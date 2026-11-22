# Xác định RTO, RPO và phân loại dữ liệu cần bảo vệ

Khi một ứng dụng ngừng hoạt động hoặc dữ liệu bị hỏng, đội kỹ thuật cần biết phải khôi phục dịch vụ trong bao lâu và có thể chấp nhận mất bao nhiêu dữ liệu. Một hệ thống bán hàng có thể chịu được vài giờ gián đoạn vào thời điểm ít giao dịch, nhưng không thể mất dữ liệu đơn hàng đã thanh toán. Một kho phân tích có thể chấp nhận khôi phục chậm hơn và dựng lại dữ liệu từ nguồn gốc. Nếu mọi hệ thống đều được sao lưu theo cùng một lịch, tổ chức có thể chi quá nhiều cho dữ liệu ít quan trọng hoặc bảo vệ không đủ cho dữ liệu thiết yếu.

Hai mục tiêu thường dùng để diễn đạt yêu cầu khôi phục là:

- **Recovery Time Objective (RTO):** khoảng thời gian gián đoạn tối đa mà nghiệp vụ chấp nhận trước khi dịch vụ phải được khôi phục.
- **Recovery Point Objective (RPO):** khoảng thời gian dữ liệu tối đa mà nghiệp vụ chấp nhận bị mất, tính lùi từ thời điểm sự cố tới điểm dữ liệu có thể khôi phục gần nhất.

Trước khi chọn lịch backup, snapshot, replication hay kiến trúc đa Region, tổ chức cần xác định RTO/RPO dựa trên tác động nghiệp vụ và phân loại dữ liệu cần bảo vệ. Đây là nền tảng để chọn dịch vụ AWS, thiết kế giải pháp an toàn, có khả năng phục hồi và kiểm soát chi phí trong hệ sinh thái **CLOUD_PROVIDERS_AWS**.

## 1. Vì sao phải xác định RTO và RPO trước?

Sao lưu là một hoạt động kỹ thuật; khả năng khôi phục là kết quả nghiệp vụ cần đạt. Có bản backup không đồng nghĩa ứng dụng sẽ hoạt động trở lại đúng hạn. Tổ chức có thể có snapshot nhưng thiếu KMS key để giải mã, thiếu IAM role, thiếu AMI hoặc artifact triển khai, chưa tạo lại VPC, chưa khôi phục DNS hoặc không có người trực để thực hiện failover.

RTO và RPO giúp trả lời hai câu hỏi độc lập:

1. **Dịch vụ được phép ngừng bao lâu?** Câu trả lời quyết định tốc độ cần thiết để phát hiện sự cố, quyết định khôi phục, tạo hạ tầng, khôi phục dữ liệu, xác minh và chuyển traffic.
2. **Dữ liệu được phép mất bao nhiêu?** Câu trả lời quyết định tần suất backup, mức độ liên tục của replication, khả năng point-in-time recovery và cách xử lý giao dịch đang diễn ra.

Nếu không xác định hai mục tiêu này, nhóm kỹ thuật thường chọn giải pháp theo thói quen, chẳng hạn backup hàng đêm cho mọi database hoặc triển khai multi-Region cho mọi ứng dụng. Cách làm đó có thể tạo chi phí lớn nhưng vẫn không đáp ứng yêu cầu quan trọng nhất của nghiệp vụ.

## 2. RTO là gì?

RTO là khoảng thời gian tối đa từ lúc dịch vụ bị gián đoạn đến lúc dịch vụ được khôi phục ở mức đáp ứng yêu cầu đã thống nhất. RTO được xác định bởi tổ chức dựa trên tác động của downtime, không phải một cam kết mặc định do AWS áp dụng cho mọi workload.

Ví dụ, hệ thống báo cáo nội bộ có thể có RTO 8 giờ. Nếu sự cố bắt đầu lúc 09:00, mục tiêu là khôi phục dịch vụ trước 17:00 cùng ngày. Một hệ thống xử lý thanh toán có thể cần RTO 15 phút; thời gian đó buộc đội kỹ thuật chuẩn bị sẵn hạ tầng, dữ liệu và quy trình chuyển đổi.

RTO không chỉ là thời gian chạy lệnh restore. Một kế hoạch khôi phục thường tiêu tốn thời gian cho:

- Phát hiện và xác nhận sự cố.
- Kích hoạt quy trình, thông báo và ra quyết định.
- Chuẩn bị account, Region, network, IAM và tài nguyên phụ thuộc.
- Khôi phục dữ liệu và cấu hình.
- Khởi động ứng dụng, kiểm tra tính toàn vẹn và health check.
- Chuyển traffic hoặc cho người dùng kết nối lại.
- Xác nhận nghiệp vụ hoạt động và xử lý các giao dịch tồn đọng.

Ví dụ phân rã RTO 60 phút:

| Công việc | Thời gian dự kiến |
|---|---:|
| Phát hiện, xác nhận và tuyên bố sự cố | 5 phút |
| Kích hoạt runbook và chuẩn bị môi trường | 10 phút |
| Khôi phục dữ liệu hoặc chuyển sang replica | 20 phút |
| Khởi động ứng dụng và kiểm tra | 15 phút |
| Chuyển traffic, xác nhận nghiệp vụ | 10 phút |
| **Tổng** | **60 phút** |

Đây là ngân sách thời gian tham khảo. Nếu một bước phụ thuộc vào thao tác thủ công, phê duyệt ngoài giờ hoặc quota chưa được chuẩn bị, thời gian thực tế có thể vượt mục tiêu.

## 3. RPO là gì?

RPO là khoảng thời gian dữ liệu tối đa mà tổ chức chấp nhận mất. RPO được đo từ thời điểm xảy ra sự cố lùi về điểm dữ liệu gần nhất mà hệ thống có thể khôi phục một cách hợp lệ.

Ví dụ, RPO 15 phút nghĩa là sau sự cố, dữ liệu khôi phục không được cũ hơn quá 15 phút so với thời điểm gián đoạn. Nếu hệ thống chỉ tạo snapshot mỗi 24 giờ, RPO thực tế có thể gần 24 giờ, trừ khi có cơ chế log backup, continuous backup hoặc replication bổ sung.

RPO không đơn giản là tần suất tạo backup. Cần tính cả:

- Khoảng cách giữa các lần backup hoặc điểm phục hồi.
- Độ trễ replication và thời gian đồng bộ.
- Thời điểm dữ liệu được commit ở nguồn.
- Khả năng phục hồi transaction log hoặc point-in-time recovery.
- Khoảng thời gian mà bản sao lưu có thể bị lỗi hoặc chưa hoàn tất.
- Mức độ nhất quán giữa nhiều hệ thống dữ liệu liên quan.

Ví dụ, một database có snapshot mỗi giờ và transaction log được lưu liên tục có thể hỗ trợ phục hồi tới một thời điểm gần sự cố hơn snapshot gần nhất. Ngược lại, nếu replication bị lag 20 phút trong khi RPO mục tiêu là 5 phút, hệ thống không đạt mục tiêu dù replication đang hoạt động.

## 4. Phân biệt RTO, RPO, MTTR và MTD

Các khái niệm này có liên quan nhưng không thay thế nhau.

| Thuật ngữ | Ý nghĩa | Cách dùng |
|---|---|---|
| RTO | Thời gian gián đoạn tối đa nghiệp vụ chấp nhận | Đặt mục tiêu khôi phục dịch vụ |
| RPO | Mức mất dữ liệu tối đa nghiệp vụ chấp nhận | Đặt mục tiêu điểm dữ liệu có thể khôi phục |
| MTTR | Thời gian trung bình để sửa chữa hoặc khôi phục sau lỗi, theo định nghĩa đo lường của tổ chức | Theo dõi hiệu quả vận hành thực tế |
| MTD / MTPD | Thời gian gián đoạn tối đa mà nghiệp vụ có thể chịu trước khi hậu quả không thể chấp nhận | Xác định giới hạn sống còn của quy trình |
| WRT | Thời gian cần để kiểm tra dữ liệu, đối soát và hoàn tất công việc sau khi dịch vụ kỹ thuật đã khôi phục | Tính thời gian trở lại hoạt động nghiệp vụ đầy đủ |

RTO cộng với WRT phải nằm trong MTD/MTPD: RTO + WRT ≤ MTD/MTPD. Một tổ chức có thể đặt RTO kỹ thuật 2 giờ nhưng cần thêm 1 giờ để đối soát giao dịch, trong khi MTD là 4 giờ. Khi lập kế hoạch, phải nói rõ “khôi phục dịch vụ” có nghĩa là API đã phản hồi hay nghiệp vụ đã có thể tiếp tục an toàn.

MTTR là chỉ số thực tế trung bình, còn RTO là mục tiêu tối đa cần đạt trong kịch bản đã xác định. Nếu MTTR trung bình là 30 phút nhưng có những lần khôi phục mất 4 giờ, không thể kết luận RTO 1 giờ luôn được đáp ứng.

## 5. Đọc RTO và RPO trên cùng một trục thời gian

Giả sử sự cố xảy ra lúc 14:00. Điểm dữ liệu gần nhất có thể khôi phục được ghi nhận lúc 13:50. Dịch vụ hoạt động trở lại lúc 14:40.

- Khoảng dữ liệu từ 13:50 đến 14:00 là 10 phút, tương ứng RPO thực tế của lần khôi phục.
- Khoảng thời gian từ 14:00 đến 14:40 là 40 phút, tương ứng downtime thực tế.

~~~mermaid
flowchart LR
    A["13:50<br/>Điểm dữ liệu khôi phục"] --> B["14:00<br/>Sự cố"]
    B --> C["14:40<br/>Dịch vụ phục hồi"]
    A --- D["RPO thực tế: 10 phút"]
    B --- E["RTO thực tế: 40 phút"]
~~~

Hai khoảng thời gian mô tả hai loại tổn thất khác nhau. Có thể có RTO ngắn nhưng RPO dài, ví dụ ứng dụng chuyển sang máy chủ dự phòng rất nhanh nhưng dữ liệu chỉ được sao chép mỗi giờ. Cũng có thể có RPO rất ngắn nhưng RTO dài, ví dụ dữ liệu được replication liên tục sang Region khác nhưng nhóm vận hành mất nhiều giờ để dựng lại ứng dụng.

Vì vậy, không dùng một chỉ số thay cho chỉ số còn lại và không giả định kiến trúc đáp ứng RPO tự động đáp ứng RTO.

## 6. Business Impact Analysis: xác định tác động nghiệp vụ

Business Impact Analysis (BIA) là quá trình xác định các hoạt động nghiệp vụ quan trọng, hậu quả khi chúng gián đoạn và thời gian mà tổ chức có thể chịu được. BIA giúp chuyển yêu cầu từ ngôn ngữ nghiệp vụ sang mục tiêu kỹ thuật.

Nên thực hiện BIA cùng chủ sở hữu nghiệp vụ, kiến trúc sư, đội vận hành, bảo mật, pháp chế/tuân thủ và các nhóm phụ thuộc. Đội kỹ thuật không nên tự quyết RTO/RPO chỉ dựa trên khả năng backup hiện có.

### 6.1. Các chiều tác động cần xem xét

| Chiều tác động | Câu hỏi cần đặt ra | Ví dụ |
|---|---|---|
| Tài chính | Mỗi phút hoặc mỗi giờ gián đoạn gây mất doanh thu hay phát sinh chi phí bao nhiêu? | Không xử lý được thanh toán, hoàn tiền hoặc đặt hàng |
| Khách hàng và danh tiếng | Người dùng có thể chuyển sang dịch vụ khác hoặc mất niềm tin không? | Cổng khách hàng không thể đăng nhập |
| Vận hành | Quy trình nội bộ nào bị dừng hoặc phải chuyển sang làm thủ công? | Kho vận không nhận được lệnh xuất hàng |
| Pháp lý và tuân thủ | Có nghĩa vụ về thời hạn khôi phục, tính toàn vẹn hoặc lưu giữ dữ liệu không? | Hồ sơ giao dịch cần được bảo toàn và truy xuất |
| An toàn và sức khỏe | Sự cố có ảnh hưởng tới con người hoặc hoạt động an toàn không? | Hệ thống cảnh báo vận hành bị gián đoạn |
| Phụ thuộc | Dịch vụ khác có dừng theo không? | Identity, DNS hoặc API dùng chung không hoạt động |

Tác động có thể tăng không tuyến tính theo thời gian. Một hệ thống có thể chịu được 30 phút downtime, nhưng sau 2 giờ sẽ bỏ lỡ cutoff thanh toán hoặc chuyến giao hàng; sau 8 giờ có thể vi phạm hợp đồng. Vì vậy, không nên suy ra RTO bằng một mức trung bình đơn giản.

### 6.2. Xác định ngưỡng chấp nhận

Với mỗi quy trình, hỏi:

1. Bao lâu sau khi ngừng hoạt động thì bắt đầu gây hậu quả đáng kể?
2. Thời điểm nào hậu quả trở nên không thể chấp nhận?
3. Có thể vận hành thủ công hoặc dùng quy trình thay thế trong bao lâu?
4. Dữ liệu nào có thể tái tạo từ nguồn khác, dữ liệu nào không thể tạo lại?
5. Nếu khôi phục một phần dữ liệu, nghiệp vụ có thể tiếp tục không?
6. Có thời điểm cao điểm, cutoff hoặc mùa vụ khiến yêu cầu thay đổi không?

Ghi lại giả định, nguồn số liệu và người phê duyệt. RTO/RPO là cam kết nội bộ cần có chủ sở hữu, ngày hiệu lực và lịch rà soát.

## 7. Phân loại dữ liệu cần bảo vệ

Không phải mọi dữ liệu đều cần cùng một mức bảo vệ. Phân loại giúp xác định dữ liệu nào cần backup thường xuyên, dữ liệu nào cần immutable copy, dữ liệu nào có thể tái tạo và dữ liệu nào phải giữ theo yêu cầu pháp lý.

Nên đánh giá ít nhất bốn khía cạnh:

### 7.1. Tính bảo mật (Confidentiality)

Xác định hậu quả nếu người không được phép đọc dữ liệu. Ví dụ:

- Public: dữ liệu đã được phép công bố.
- Internal: tài liệu vận hành hoặc cấu hình nội bộ.
- Confidential: thông tin khách hàng, hợp đồng, dữ liệu tài chính.
- Restricted: credential, dữ liệu định danh nhạy cảm hoặc hồ sơ chịu kiểm soát nghiêm ngặt.

Tên phân loại là ví dụ; tổ chức cần dùng taxonomy chính thức của mình. Mức bảo mật ảnh hưởng tới encryption, IAM, KMS key, vị trí lưu backup, quyền restore và quy trình xử lý bản sao.

### 7.2. Tính toàn vẹn (Integrity)

Xác định hậu quả nếu dữ liệu bị sửa sai, xóa nhầm hoặc khôi phục từ một bản đã bị hỏng. Một số dữ liệu cần audit trail, checksum, versioning hoặc khả năng point-in-time recovery.

Ví dụ, số dư tài khoản và giao dịch thanh toán yêu cầu tính toàn vẹn cao. File cache hoặc dữ liệu tính toán tạm thời có thể được tái tạo nếu mất.

### 7.3. Tính sẵn sàng (Availability)

Xác định thời gian dữ liệu hoặc dịch vụ có thể không truy cập được. Khía cạnh này liên kết trực tiếp với RTO, RPO và chiến lược DR.

### 7.4. Nghĩa vụ lưu giữ và xóa dữ liệu

Một số dữ liệu cần lưu nhiều năm; dữ liệu khác phải xóa sau khi hết mục đích hoặc thời hạn. Backup không được trở thành nơi giữ dữ liệu vô thời hạn trái với chính sách. Phải cân bằng retention, legal hold, quyền xóa, yêu cầu điều tra và quy định bảo vệ dữ liệu.

## 8. Phân loại dữ liệu theo khả năng khôi phục

Ngoài mức nhạy cảm, hãy phân loại theo vai trò trong workload:

| Nhóm dữ liệu | Ví dụ | Cách bảo vệ thường dùng |
|---|---|---|
| Transactional / system of record | Đơn hàng, thanh toán, hồ sơ khách hàng | Backup nhất quán, PITR, replication và kiểm tra đối soát |
| Operational state | Trạng thái workflow, job, hàng đợi hoặc phiên làm việc | Backup hoặc replication tùy khả năng tái tạo và mức mất dữ liệu chấp nhận |
| Configuration | Tham số ứng dụng, IaC, DNS, policy | Version control, IaC repository, backup cấu hình và quy trình khôi phục |
| Identity and access | IAM policy, role trust, identity configuration | IaC, audit, backup/export cấu hình và quyền khẩn cấp |
| Secrets and cryptographic material | Secret, KMS key policy, certificate metadata | Quản lý bằng dịch vụ chuyên biệt, backup/replication phù hợp và kiểm soát quyền |
| Application artifacts | Container image, package, binary, deployment manifest | Artifact repository, versioning, replication và provenance |
| Logs and audit records | CloudTrail, application logs, security events | Lưu trữ tập trung, retention, bảo vệ chống sửa/xóa và truy xuất |
| Derived / cache data | Cache, index có thể dựng lại, báo cáo tổng hợp | Có thể tái tạo từ nguồn chuẩn; backup theo chi phí và thời gian dựng lại |

Một tập dữ liệu có thể đồng thời thuộc nhiều nhóm. Ví dụ, file export chứa dữ liệu khách hàng là derived data nhưng vẫn có mức Confidential. Vì vậy, không được dùng khả năng tái tạo để bỏ qua yêu cầu bảo mật hoặc retention.

### Dữ liệu nguồn và dữ liệu dẫn xuất

Hãy xác định đâu là **authoritative source**. Nếu một báo cáo có thể tạo lại từ database giao dịch và event log, có thể không cần backup từng bản báo cáo. Nhưng phải bảo vệ database và event log đủ tốt để quá trình tái tạo khả thi.

Với dữ liệu dẫn xuất có chi phí tạo lại lớn, thời gian rebuild có thể khiến RTO không đạt. Khi đó, backup hoặc snapshot của dữ liệu dẫn xuất vẫn có giá trị dù nó không phải nguồn chuẩn.

## 9. Xếp hạng workload theo mức độ quan trọng

Sau BIA và phân loại dữ liệu, tổ chức có thể xây dựng các tier để thống nhất mục tiêu. Bảng dưới đây là ví dụ tham khảo, không phải tiêu chuẩn bắt buộc của AWS.

| Tier ví dụ | Mức độ | RTO mục tiêu | RPO mục tiêu | Ví dụ |
|---|---|---:|---:|---|
| Tier 0 | Mission critical | 1–5 phút | Gần 0–1 phút | Thanh toán lõi, identity dùng chung |
| Tier 1 | Business critical | 15–60 phút | 5–15 phút | Đặt hàng, quản lý tồn kho |
| Tier 2 | Important | 4 giờ | 1 giờ | Portal nội bộ, hệ thống báo cáo vận hành |
| Tier 3 | Standard | 24 giờ | 24 giờ | Môi trường thử nghiệm, dữ liệu có thể dựng lại |
| Tier 4 | Low priority | 72 giờ hoặc theo kế hoạch | Theo khả năng tái tạo | Sandbox hoặc workload tạm thời |

Mục tiêu cần được xác nhận với chủ sở hữu nghiệp vụ và kiểm chứng bằng thử nghiệm. Không gán Tier 0 chỉ vì hệ thống dùng database lớn; cũng không xếp Tier 3 chỉ vì môi trường không phục vụ khách hàng trực tiếp.

Một workload có thể có các thành phần với yêu cầu khác nhau. Ví dụ, frontend có thể tái tạo nhanh, trong khi database giao dịch cần RPO rất thấp. Hãy đặt mục tiêu cho toàn workload và các data store quan trọng, rồi kiểm tra rằng các thành phần kết hợp vẫn đạt mục tiêu chung.

## 10. Lập bản đồ phụ thuộc trước khi đặt mục tiêu

Khôi phục dữ liệu không đủ để khôi phục ứng dụng. Một workload có thể phụ thuộc vào:

- VPC, subnet, route table, security group, NACL và network firewall.
- IAM role, instance profile, KMS key và key policy.
- DNS, certificate, secrets và parameter.
- AMI, container image, package repository và source code.
- Database, queue, object storage, file system và cache.
- API bên ngoài, identity provider và hệ thống thanh toán.
- Monitoring, log pipeline, deployment pipeline và quota dịch vụ.

Nếu database đã restore nhưng KMS key không thể sử dụng, ứng dụng vẫn không đọc được dữ liệu. Nếu compute được dựng lại nhưng DNS chưa chuyển, người dùng vẫn không truy cập được. Nếu IAM role thiếu quyền, restore job có thể thất bại dù backup còn nguyên.

~~~mermaid
flowchart TD
    A[Người dùng / hệ thống gọi] --> B[DNS và chứng chỉ]
    B --> C[Load balancer / API]
    C --> D[Compute: EC2 / ECS / EKS / Lambda]
    D --> E[Database / S3 / EFS / Queue]
    D --> F[IAM role và Secrets]
    E --> G[KMS key và key policy]
    D --> H[Network: VPC / subnet / route]
    I[Backup và recovery point] --> E
    J[IaC và artifact] --> C
    J --> D
~~~

Với mỗi dependency, ghi owner, Region, account, cách tạo lại, thời gian chuẩn bị và điều kiện truy cập. Mục tiêu RTO của dịch vụ phụ thuộc không nên dài hơn mục tiêu của workload chính nếu nó chặn quá trình phục hồi.

## 11. Chuyển RPO thành yêu cầu backup và replication

Sau khi xác định RPO, nhóm kỹ thuật mới chọn lịch và công nghệ bảo vệ dữ liệu.

Ví dụ tham khảo:

| RPO mục tiêu | Hướng kỹ thuật có thể xem xét |
|---|---|
| 24 giờ | Backup định kỳ hằng ngày; kiểm tra thời gian hoàn tất và khả năng restore |
| 4 giờ | Backup nhiều lần trong ngày hoặc snapshot kết hợp log backup |
| 15 phút | PITR, continuous backup hoặc replication có độ trễ được giám sát |
| 1 phút hoặc gần 0 | Replication gần thời gian thực, multi-AZ/multi-Region theo khả năng dịch vụ và cơ chế nhất quán |

Đây không phải ánh xạ cố định. Cần kiểm tra tính năng của từng dịch vụ, giới hạn Region, retention, độ trễ và khả năng phục hồi thực tế.

### Ví dụ tính tần suất backup

Giả sử một hệ thống chấp nhận mất tối đa 30 phút dữ liệu. Nếu chỉ dựa vào snapshot định kỳ, khoảng cách giữa các snapshot phải nhỏ hơn hoặc bằng 30 phút và cần có biên an toàn cho thời gian job chạy, lỗi job và độ trễ. Nếu snapshot thường mất 8 phút mới hoàn tất, lịch 30 phút không nhất thiết bảo đảm RPO 30 phút trong mọi trường hợp.

Với database hỗ trợ continuous backup/PITR, điểm khôi phục có thể gần thời điểm sự cố hơn snapshot định kỳ. Nhưng cần kiểm tra cửa sổ PITR, độ trễ log, trạng thái backup và các giới hạn riêng của engine.

### Replication không thay thế backup

Replication giúp bản sao cập nhật nhanh, nhưng lỗi logic, xóa nhầm hoặc mã độc có thể được sao chép sang đích. Backup có retention và điểm khôi phục lịch sử giúp quay về trước thời điểm dữ liệu bị hỏng. Với dữ liệu quan trọng, thường cần cả replication để giảm RTO/RPO và backup độc lập để phục hồi sau corruption hoặc destructive action.

## 12. Chuyển RTO thành yêu cầu kiến trúc và quy trình

RTO mục tiêu phải được chuyển thành các công việc có thể thực thi:

1. Phát hiện và xác định sự cố bằng monitoring, alert và runbook.
2. Quyết định failover hay restore theo tiêu chí đã thống nhất.
3. Chuẩn bị compute, network, IAM, DNS, certificate và quota.
4. Khôi phục hoặc promote data store.
5. Triển khai phiên bản ứng dụng tương thích với dữ liệu.
6. Kiểm tra health, consistency, security và luồng nghiệp vụ.
7. Chuyển traffic và xác nhận hoạt động.
8. Theo dõi ổn định, đối soát dữ liệu và đóng sự cố.

Infrastructure as Code giúp giảm thời gian tạo lại VPC, subnet, security group, load balancer, compute và các thành phần khác. Tuy nhiên, IaC chỉ giảm RTO khi module, state, artifact, quyền và quota đã được chuẩn bị và thử nghiệm ở Region khôi phục.

Nếu một bước cần con người phê duyệt, xác định người thay thế, kênh liên lạc ngoài băng và quyền khẩn cấp. Một runbook chỉ hoạt động khi người duy nhất biết mật khẩu đang nghỉ phép sẽ không đáp ứng RTO.

## 13. Chọn chiến lược DR theo RTO, RPO và chi phí

AWS Well-Architected mô tả bốn chiến lược DR thường dùng cho workload đa Region. Chúng có mức độ sẵn sàng, độ phức tạp và chi phí tăng dần.

| Chiến lược | Đặc điểm | RTO/RPO thường thấy | Chi phí tương đối |
|---|---|---|---|
| Backup and restore | Backup dữ liệu; dựng hạ tầng và restore khi có sự cố | Thường tính bằng giờ; có thể thấp hơn nếu dùng PITR và tự động hóa | Thấp |
| Pilot light | Thành phần lõi và dữ liệu được chuẩn bị/replicate; compute phụ có thể tạo khi failover | RTO hàng chục phút; RPO phụ thuộc replication | Trung bình |
| Warm standby | Một phiên bản thu nhỏ nhưng hoạt động được luôn tồn tại ở Region dự phòng | RTO vài phút; RPO thường thấp nếu dữ liệu replicate liên tục | Cao |
| Multi-site active/active | Nhiều Region cùng phục vụ traffic | RTO có thể gần 0; RPO gần 0 nếu kiến trúc dữ liệu đáp ứng | Rất cao |

Các con số chỉ mang tính định hướng. Kết quả thực tế phụ thuộc dịch vụ, dữ liệu, automation, quota, độ trễ mạng, cơ chế failover và thử nghiệm. Active/active không tự động giải quyết xung đột ghi dữ liệu hoặc corruption; vẫn cần thiết kế consistency, conflict resolution và point-in-time recovery.

Không phải mọi sự cố đều cần DR đa Region. Multi-AZ có thể đủ để chịu lỗi phần cứng hoặc một Availability Zone. Nếu yêu cầu chỉ là phục hồi sau xóa nhầm hoặc ransomware, backup bất biến và khả năng restore có thể quan trọng hơn việc giữ một Region thứ hai luôn chạy.

## 14. Các dịch vụ AWS hỗ trợ bảo vệ dữ liệu

Chọn dịch vụ dựa trên loại tài nguyên, yêu cầu nhất quán, RTO/RPO và cách khôi phục.

| Dịch vụ / năng lực | Vai trò | Điểm cần xác minh |
|---|---|---|
| AWS Backup | Quản lý backup plan, vault, lifecycle, copy và restore cho nhiều dịch vụ được hỗ trợ | Resource coverage, backup window, retention, Region/account copy và restore test |
| EBS snapshots | Backup volume block storage | Application consistency, snapshot lifecycle, copy và KMS key |
| EC2 AMI | Lưu image cấu hình máy để khởi tạo instance mới | Phụ thuộc volume, launch configuration, driver và account/Region |
| RDS automated backups / snapshots | Backup database và point-in-time restore theo engine hỗ trợ | Retention, PITR window, snapshot copy, restore time và failover |
| Aurora backups / Global Database | Backup, PITR và replication cho kiến trúc Aurora | Engine/version, replication lag, promotion và consistency |
| DynamoDB PITR / on-demand backup | Khôi phục bảng theo thời điểm hoặc bản backup | Retention PITR, restore target và kiểm tra index/stream phụ thuộc |
| S3 Versioning / replication | Giữ nhiều version object và bản sao ở bucket khác | Delete marker, replication status, Object Lock và khả năng khôi phục |
| EFS / FSx backup | Bảo vệ file system theo tính năng dịch vụ | Restore target, throughput, permission và application consistency |
| AWS Elastic Disaster Recovery | Replicate server và hỗ trợ recovery vào AWS | Agent, staging area, test drill, launch settings và RTO thực tế |
| AWS Backup Vault Lock | Bảo vệ recovery point khỏi bị xóa hoặc thay đổi trái phép theo chế độ khóa | Governance/Compliance mode, grace time và retention |

Không phải mọi resource type đều hỗ trợ cùng tính năng hoặc cùng lịch backup. Kiểm tra feature availability theo Region và dịch vụ trước khi cam kết RTO/RPO.

## 15. Thiết kế retention và bảo vệ bản sao lưu

Retention phải đáp ứng cả khả năng phục hồi và nghĩa vụ lưu giữ. Giữ quá ít điểm khôi phục có thể khiến tổ chức không quay lại được trước khi phát hiện corruption. Giữ quá lâu có thể làm tăng chi phí và xung đột với chính sách xóa dữ liệu.

Một chính sách retention nên xác định:

- Tần suất backup theo RPO.
- Số điểm khôi phục gần đây cần giữ.
- Retention hằng ngày, hằng tuần, hằng tháng và hằng năm.
- Thời gian giữ bản sao ở Region/account khác.
- Quy tắc chuyển storage tier nếu dịch vụ hỗ trợ.
- Yêu cầu legal hold hoặc immutability.
- Quy trình xóa hết hạn và kiểm tra chi phí.

### Chống xóa hoặc mã hóa backup bởi attacker

Nếu attacker chiếm quyền quản trị account và xóa cả production lẫn backup, kế hoạch DR có thể thất bại. Cân nhắc:

- Backup copy sang account bảo mật riêng.
- Cross-Region copy để tách fault domain.
- AWS Backup Vault Lock với Governance hoặc Compliance mode theo yêu cầu.
- IAM/SCP hạn chế quyền xóa vault, recovery point hoặc thay đổi backup plan.
- MFA, break-glass role và phê duyệt nhiều người cho thao tác nguy hiểm.
- S3 Object Lock hoặc cơ chế bảo vệ bất biến phù hợp với loại dữ liệu.
- Giám sát thay đổi backup policy, vault, KMS và quyền truy cập.

Compliance mode của AWS Backup Vault Lock có thời gian grace trước khi khóa trở nên bất biến. Khi hết grace time, lock không thể bị gỡ hoặc sửa; recovery point được giữ đến hết lifecycle. Cần kiểm tra retention và chi phí trước khi bật chế độ này.

### Bảo vệ KMS key và quyền giải mã

Backup được mã hóa nhưng KMS key bị xóa, disabled hoặc key policy không cho phép restore thì dữ liệu có thể không sử dụng được. Kế hoạch DR phải bảo vệ:

- Key ARN và Region nơi key tồn tại.
- Key policy, grants và IAM role phục hồi.
- Quy trình enable/restore key và thời gian chờ deletion nếu có.
- Cách dùng key ở Region khôi phục.
- Quyền truy cập key khi account nguồn bị cô lập.

Không xóa KMS key chỉ vì workload đã bị terminate. Hãy xác định retention của backup và các dependency trước khi lập lịch xóa key.

## 16. Phân loại dữ liệu thành ma trận bảo vệ

Ví dụ một nền tảng thương mại điện tử có thể lập ma trận ban đầu như sau. Mục tiêu là ví dụ để thảo luận; chủ sở hữu nghiệp vụ phải phê duyệt các con số cuối cùng.

| Dữ liệu / workload | Phân loại | Tính tái tạo | RTO đề xuất | RPO đề xuất | Biện pháp |
|---|---|---|---:|---:|---|
| Database đơn hàng | Confidential, integrity cao | Không thể tái tạo đầy đủ | 30 phút | 5 phút | PITR, replication, backup cross-account |
| Database thanh toán | Restricted, integrity rất cao | Không thể tái tạo từ cache | 15 phút | Gần 0–1 phút | HA, log/replication liên tục, backup bất biến, đối soát |
| Catalog sản phẩm | Internal/Confidential | Có thể dựng lại một phần | 2 giờ | 15 phút | Backup định kỳ, snapshot và export |
| File hóa đơn | Confidential, retention dài | Không thể tạo lại hoàn toàn | 4 giờ | 1 giờ | S3 Versioning, replication, Object Lock theo chính sách |
| Cache phiên | Internal | Có thể tái tạo | 4 giờ | 1 giờ hoặc bỏ qua | Rebuild cache từ nguồn chuẩn |
| Báo cáo phân tích | Internal | Có thể chạy lại từ nguồn | 24 giờ | 24 giờ | Backup tùy chi phí, giữ dữ liệu nguồn và pipeline |
| IaC và artifact | Internal | Có thể lấy từ repository nếu độc lập | 1 giờ | Theo commit đã phát hành | Git, artifact repository, replication và immutable release |
| Audit logs | Confidential/Restricted | Không thể tái tạo | 8 giờ truy cập | Theo yêu cầu lưu giữ | Log archive account, retention và Object Lock phù hợp |

Nếu hai data store có quan hệ transaction, không chỉ đặt RPO riêng lẻ. Phải xác định cách khôi phục đồng bộ để tránh database đơn hàng cho biết đã thanh toán trong khi ledger thanh toán không có giao dịch tương ứng.

## 17. Ví dụ thực hành: xác định mục tiêu cho hệ thống Orders

Giả sử hệ thống Orders gồm API trên ECS, database RDS, queue SQS, object invoice trên S3, cache và một dịch vụ thanh toán bên ngoài.

### Bước 1: Xác định hoạt động nghiệp vụ

Orders nhận đơn hàng, kiểm tra tồn kho, tạo giao dịch thanh toán và lưu hóa đơn. Nếu API ngừng, người dùng không thể đặt hàng. Nếu dữ liệu đơn hàng mất, doanh nghiệp có thể không biết đơn nào đã được chấp nhận hoặc thanh toán.

### Bước 2: Phân loại dữ liệu

- RDS Orders: nguồn chuẩn cho đơn hàng, Confidential và integrity cao.
- Payment reference: Restricted, phải đối soát với nhà cung cấp thanh toán.
- S3 invoices: Confidential, có yêu cầu retention.
- SQS messages: trạng thái workflow; cần xác định message nào có thể tạo lại từ database.
- Cache: dữ liệu dẫn xuất, có thể rebuild.
- IaC và container image: cần bảo vệ để có thể triển khai đúng phiên bản.

### Bước 3: Chọn mục tiêu ban đầu

| Thành phần | RTO | RPO | Lý do |
|---|---:|---:|---|
| Orders API | 30 phút | Theo data store | Cần tiếp tục nhận request sau khi backend sẵn sàng |
| Orders database | 30 phút | 5 phút | Không thể mất nhiều giao dịch đã xác nhận |
| Invoice bucket | 4 giờ | 1 giờ | Có thể xử lý một số quy trình tạm thời nhưng không được mất file đã phát hành |
| Cache | 4 giờ | Không yêu cầu dữ liệu cũ | Rebuild từ database |
| IaC/image | 1 giờ | Theo commit/release | Cần dựng lại workload đúng version |

### Bước 4: Xác định phụ thuộc

RDS cần subnet group, security group, KMS key, parameter/secret và quyền restore. ECS cần cluster, task definition, image, task role, load balancer và secret. API cần DNS, certificate và tích hợp payment provider. Queue cần xác định message đang in-flight và cách chống xử lý trùng.

### Bước 5: Kiểm thử

Thực hiện restore vào môi trường cô lập, kiểm tra dữ liệu, chạy test đặt hàng, đối soát thanh toán, xác minh invoice và đo thời gian từ lúc bắt đầu tới khi nghiệp vụ hoạt động. Nếu mất 55 phút để hoàn tất trong khi RTO là 30 phút, phải điều chỉnh kiến trúc hoặc mục tiêu sau khi trao đổi với nghiệp vụ.

~~~mermaid
flowchart TD
    A[BIA: Orders] --> B[Phân loại dữ liệu và owner]
    B --> C[Đặt RTO/RPO cho API và data store]
    C --> D[Lập bản đồ dependency]
    D --> E[Chọn backup / replication / DR]
    E --> F[Restore test và failover drill]
    F --> G{Đạt RTO/RPO?}
    G -->|Không| H[Điều chỉnh kiến trúc hoặc mục tiêu]
    H --> E
    G -->|Có| I[Phê duyệt và rà soát định kỳ]
~~~

## 18. Kiểm thử khả năng khôi phục và đo kết quả

Backup job thành công chỉ xác nhận dữ liệu đã được tạo theo cơ chế dịch vụ. Nó không chứng minh ứng dụng có thể khôi phục trong RTO hoặc dữ liệu sau restore có thể dùng được.

Một chương trình kiểm thử nên có:

1. **Restore test:** khôi phục bản backup vào môi trường cô lập và xác minh dữ liệu.
2. **Point-in-time recovery test:** khôi phục về thời điểm trước lỗi giả định, kiểm tra transaction và tính nhất quán.
3. **Failover test:** chuyển workload sang môi trường dự phòng, đo thời gian và độ trễ dữ liệu.
4. **Dependency test:** kiểm tra IAM, KMS, DNS, network, certificate, secret và artifact.
5. **Application validation:** chạy health check, integration test và luồng nghiệp vụ đại diện.
6. **Access control test:** xác nhận chỉ role được phép mới có thể restore hoặc thay đổi vault.
7. **Ransomware recovery drill:** kiểm tra khả năng khôi phục từ bản backup không bị attacker xóa hoặc sửa.

Ghi nhận các mốc thời gian: detection, declaration, recovery start, data available, application ready, traffic restored và business validation complete. So sánh với RTO/RPO mục tiêu, không chỉ thời gian của một lệnh AWS Backup restore.

### Các chỉ số nên theo dõi

- Tỷ lệ backup job thành công và thất bại.
- Tuổi của recovery point mới nhất.
- Replication lag và copy job status.
- Tỷ lệ workload có backup plan đúng.
- Tỷ lệ restore test thành công.
- RTO/RPO đo được qua diễn tập.
- Số lượng ngoại lệ chưa có owner hoặc chưa được khắc phục.
- Chi phí backup storage, copy, snapshot và restore.

AWS Backup Audit Manager có thể hỗ trợ kiểm tra mức tuân thủ backup policy theo control/framework phù hợp. AWS Resilience Hub có thể giúp đánh giá resilience của workload theo kiến trúc và mục tiêu phục hồi. Các công cụ này hỗ trợ kiểm tra, nhưng không thay thế bài diễn tập restore thực tế.

## 19. Worksheet xác định RTO, RPO và phân loại dữ liệu

Với mỗi workload, ghi lại các thông tin sau và yêu cầu cả business owner lẫn technical owner xác nhận.

| Trường | Nội dung cần ghi |
|---|---|
| Workload / service | Tên ứng dụng, account, Region và môi trường |
| Business owner | Người chịu trách nhiệm nghiệp vụ |
| Technical owner | Nhóm vận hành và đầu mối khôi phục |
| Business process | Quy trình nghiệp vụ mà workload hỗ trợ |
| Impact | Tác động tài chính, khách hàng, vận hành, pháp lý |
| MTD/MTPD | Thời gian gián đoạn tối đa có thể chịu |
| RTO | Mục tiêu thời gian khôi phục đã được phê duyệt |
| WRT | Thời gian đối soát và đưa nghiệp vụ trở lại đầy đủ |
| RPO | Mức mất dữ liệu tối đa được chấp nhận |
| Data classification | Public/Internal/Confidential/Restricted hoặc taxonomy nội bộ |
| Data owner / source of truth | Chủ sở hữu và hệ thống nguồn chuẩn |
| Retention | Thời hạn lưu và yêu cầu xóa/legal hold |
| Dependencies | IAM, KMS, network, DNS, secret, artifact, dịch vụ ngoài |
| Recovery strategy | Backup/restore, pilot light, warm standby hoặc active/active |
| Evidence | Kết quả restore test, failover drill và phê duyệt |
| Review date | Ngày rà soát lại mục tiêu và kiến trúc |

Không để trống owner hoặc dependency chỉ vì hệ thống cũ chưa có tài liệu. Ghi rõ “chưa xác định” và tạo công việc xử lý có thời hạn.

## 20. Sai lầm thường gặp

### Đặt RTO/RPO theo khả năng kỹ thuật hiện có

Backup mỗi ngày không có nghĩa nghiệp vụ chỉ cần RPO 24 giờ. Bắt đầu từ tác động nghiệp vụ, sau đó đánh giá chi phí và tính khả thi của giải pháp.

### Chỉ đặt RTO cho cả ứng dụng

Database, object storage, identity, DNS và artifact có cách phục hồi khác nhau. Xác định mục tiêu cho workload và data store quan trọng, sau đó kiểm tra các thành phần phụ thuộc có đáp ứng được không.

### Cho rằng RPO bằng tần suất backup

Backup job có thể chạy trễ, thất bại hoặc chưa hoàn tất. Dùng thời điểm recovery point thực tế và replication lag để đánh giá RPO.

### Cho rằng replication thay thế backup

Replication có thể sao chép corruption hoặc thao tác xóa. Giữ điểm khôi phục lịch sử, retention độc lập và bản sao được bảo vệ.

### Backup dữ liệu nhưng quên KMS key

Thiếu quyền giải mã hoặc key bị xóa có thể khiến restore không dùng được. Bảo vệ key, policy, grants và quyền ở Region khôi phục.

### Không backup cấu hình và artifact

Có database nhưng không có image, IaC, certificate hoặc secret cần thiết thì ứng dụng vẫn không khởi động được. Đưa các dependency vào kế hoạch DR.

### Chỉ kiểm tra backup job, không kiểm tra restore

Thử khôi phục định kỳ và đo toàn bộ quy trình tới khi nghiệp vụ hoạt động.

### Chọn active/active cho mọi workload

Kiến trúc đa Region có chi phí, độ phức tạp dữ liệu và rủi ro split-brain. Chỉ dùng khi yêu cầu nghiệp vụ biện minh và tổ chức có khả năng vận hành.

### Không xét yêu cầu xóa dữ liệu

Retention quá dài có thể trái chính sách. Thiết kế lifecycle và legal hold theo yêu cầu bảo vệ dữ liệu.

### Không cập nhật mục tiêu khi nghiệp vụ thay đổi

Mùa cao điểm, sản phẩm mới, hợp đồng hoặc quy định mới có thể làm thay đổi mức chấp nhận downtime/data loss. Rà soát sau thay đổi lớn và theo lịch định kỳ.

## 21. Checklist trước khi phê duyệt kế hoạch bảo vệ dữ liệu

- [ ] Có BIA và business owner cho từng workload.
- [ ] RTO, RPO, MTD/MTPD và WRT được phân biệt rõ.
- [ ] Mục tiêu được phê duyệt dựa trên tác động nghiệp vụ và yêu cầu tuân thủ.
- [ ] Dữ liệu được phân loại theo confidentiality, integrity, availability và retention.
- [ ] Xác định nguồn dữ liệu chuẩn và dữ liệu có thể tái tạo.
- [ ] Có owner, account, Region và dependency map cho từng workload.
- [ ] Backup frequency/replication lag đáp ứng RPO với biên an toàn.
- [ ] Recovery strategy đáp ứng RTO và có nguồn lực vận hành.
- [ ] Bản backup được bảo vệ khỏi xóa/sửa trái phép và có bản sao phù hợp.
- [ ] KMS key, IAM, DNS, network, secret, certificate và artifact được tính trong DR.
- [ ] Retention phù hợp chính sách pháp lý và xóa dữ liệu.
- [ ] Có restore test, PITR test hoặc failover drill theo lịch.
- [ ] Đo RTO/RPO thực tế và lưu bằng chứng.
- [ ] Có runbook, người thay thế và kênh liên lạc khẩn cấp.
- [ ] Chi phí backup, copy, storage và DR được theo dõi.
- [ ] Rà soát lại mục tiêu khi workload hoặc nghiệp vụ thay đổi.

## 22. Ghi nhớ

RTO mô tả thời gian gián đoạn tối đa có thể chấp nhận; RPO mô tả mức mất dữ liệu tối đa có thể chấp nhận. Hai mục tiêu độc lập và phải được xác định cho từng workload dựa trên BIA, yêu cầu pháp lý, dữ liệu và dependency. Không suy ra mục tiêu từ lịch backup đang có.

Phân loại dữ liệu theo bảo mật, toàn vẹn, sẵn sàng, khả năng tái tạo và retention giúp xác định dữ liệu nào cần bảo vệ thường xuyên, dữ liệu nào cần immutable copy và dữ liệu nào có thể dựng lại. Sau đó lập bản đồ IAM, KMS, network, DNS, secrets, artifact và dịch vụ phụ thuộc để kế hoạch khôi phục bao phủ toàn workload.

Cuối cùng, chọn backup/restore, pilot light, warm standby hoặc active/active theo mục tiêu và chi phí; kiểm thử restore/failover định kỳ; đo RTO/RPO thực tế và cập nhật kế hoạch khi nghiệp vụ thay đổi. Chỉ khi dữ liệu và toàn bộ dịch vụ có thể được khôi phục đúng hạn, tổ chức mới có thể tin cậy vào khả năng phục hồi của hệ thống AWS.

## Tài liệu tham khảo

- [AWS Well-Architected: Define Recovery Objectives for Downtime and Data Loss](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel13-bp01.html)
- [AWS Well-Architected: Use Defined Recovery Strategies](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_planning_for_recovery_disaster_recovery.html)
- [Disaster Recovery of Workloads on AWS: Recovery in the Cloud](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/welcome.html)
- [AWS Prescriptive Guidance: Defining Your Disaster Recovery Strategy](https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-database-disaster-recovery/defining.html)
- [AWS Backup: Backup Plans](https://docs.aws.amazon.com/aws-backup/latest/devguide/about-backup-plans.html)
- [AWS Backup: Plan Options and Configuration](https://docs.aws.amazon.com/aws-backup/latest/devguide/plan-options-and-configuration.html)
- [AWS Backup: Vault Lock](https://docs.aws.amazon.com/aws-backup/latest/devguide/vault-lock.html)
- [AWS Backup: Cross-Account Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/create-cross-account-backup.html)
- [AWS Backup: Cross-Region Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/cross-region-backup.html)
- [AWS Backup Audit Manager](https://docs.aws.amazon.com/aws-backup/latest/devguide/aws-backup-audit-manager.html)
- [Amazon RDS: Backup and Restore](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_CommonTasks.BackupRestore.html)
- [Amazon DynamoDB: Backups and Point-in-Time Recovery](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/BackupRestore.html)
- [Amazon S3: Using Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html)
- [Amazon S3: Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/what-is-drs.html)
- [AWS Resilience Hub](https://docs.aws.amazon.com/resilience-hub/latest/userguide/what-is.html)

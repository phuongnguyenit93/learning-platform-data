# Tiêu chí chọn Region và yêu cầu lưu trú dữ liệu

Trong AWS, chọn **Region** là một quyết định kiến trúc có ảnh hưởng lâu dài đến trải nghiệm người dùng, khả năng khôi phục sự cố, chi phí vận hành và việc tuân thủ quy định về dữ liệu. Một Region gần người dùng có thể giảm độ trễ, nhưng chưa chắc cung cấp đủ dịch vụ hoặc đáp ứng yêu cầu dữ liệu của tổ chức. Vì vậy, cần đánh giá Region trước khi triển khai hạ tầng.

Bài học thuộc chương **Tổng quan AWS** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung vận dụng kiến thức về Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless để giúp người học lựa chọn, thiết kế và triển khai ứng dụng an toàn, có giám sát, có phương án phục hồi và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt Region, Availability Zone (AZ) và edge location; giải thích phạm vi ảnh hưởng của từng lớp hạ tầng.
2. Xây dựng bộ tiêu chí chọn Region có xét đến độ trễ, dịch vụ, tính sẵn sàng, chi phí, vận hành và tính bền vững.
3. Phân biệt **data residency** (lưu trú dữ liệu), **data localization** (yêu cầu lưu dữ liệu tại một địa bàn xác định), **data sovereignty** (quyền tài phán và sự kiểm soát pháp lý đối với dữ liệu) với yêu cầu bảo mật.
4. Liệt kê các bản sao dữ liệu dễ bị bỏ sót: bản sao dự phòng, snapshot, log, cache, dữ liệu phân tích và bản sao khôi phục thảm họa (DR).
5. Đề xuất kiến trúc một Region nhiều AZ hoặc nhiều Region dựa trên mục tiêu RTO/RPO và phạm vi địa lý được phép.
6. Lập kế hoạch kiểm chứng vị trí tài nguyên và cơ chế ngăn triển khai sai Region.

## 2. Hiểu đúng về vị trí hạ tầng AWS

**Region** là một khu vực địa lý AWS cung cấp tài nguyên và dịch vụ, có định danh như **ap-southeast-1** (Singapore), **ap-northeast-1** (Tokyo) hoặc **eu-central-1** (Frankfurt). Mỗi Region thường có nhiều **Availability Zone** tách biệt về hạ tầng vật lý. AZ dùng để xây dựng khả năng chịu lỗi trước sự cố cục bộ trong Region.

**Edge location** phục vụ các dịch vụ phân phối hoặc định tuyến gần người dùng, chẳng hạn Amazon CloudFront. Edge location không đồng nghĩa với Region chứa cơ sở dữ liệu hay các máy chủ ứng dụng. Một ứng dụng có thể đặt cơ sở dữ liệu tại một Region nhưng vẫn lưu cache nội dung tại nhiều địa điểm ngoài Region nếu cấu hình dịch vụ phân phối nội dung cho phép.

| Khái niệm | Phạm vi chính | Vai trò kiến trúc | Điều cần nhớ |
|---|---|---|---|
| Region | Khu vực địa lý | Vị trí triển khai dịch vụ, phạm vi dữ liệu và khôi phục cấp Region | Chọn Region không tự động kiểm soát mọi bản sao dữ liệu của mọi dịch vụ |
| Availability Zone | Miền lỗi độc lập trong một Region | Triển khai ứng dụng và dữ liệu dự phòng ở nhiều AZ | Multi-AZ bảo vệ trước lỗi cấp AZ, không bảo đảm chịu được sự cố toàn Region |
| Edge location | Điểm hiện diện gần người dùng | CDN, tăng tốc truy cập, xử lý một phần lưu lượng tại biên | Nội dung cache và một số log có thể phát sinh ở nơi khác với Region gốc |

Ví dụ, website thương mại điện tử có thể đặt Amazon ECS hoặc EC2 ở hai AZ trong một Region, đặt Amazon RDS ở chế độ Multi-AZ, dùng Amazon S3 cho ảnh sản phẩm và CloudFront cho phân phối ảnh. Người dùng có thể nhận ảnh từ edge location gần mình, trong khi truy vấn giỏ hàng vẫn đến hệ thống tại Region chính.

~~~mermaid
flowchart TB
    U["Người dùng"] --> EDGE["CloudFront / edge location"]
    EDGE --> ALB["Application Load Balancer\nRegion chính"]
    subgraph R["Region chính: phạm vi triển khai"]
        subgraph A["AZ A"]
            APP1["Ứng dụng"]
        end
        subgraph B["AZ B"]
            APP2["Ứng dụng"]
        end
        ALB --> APP1
        ALB --> APP2
        DB["Cơ sở dữ liệu Multi-AZ"]
        S3["S3 bucket cùng Region"]
        APP1 --> DB
        APP2 --> DB
        APP1 --> S3
        APP2 --> S3
    end
    R -. "Chỉ sao chép khi được phép và cấu hình" .-> DR["Region dự phòng"]
~~~

Sơ đồ minh họa luồng xử lý; vị trí lưu trữ cache, log, dữ liệu vận hành và tính năng thực tế phải được kiểm tra theo từng dịch vụ AWS.

## 3. Bộ tiêu chí quyết định Region

Không nên chọn Region chỉ vì khoảng cách trên bản đồ. Hãy phân thành **điều kiện bắt buộc** (Region phải đáp ứng mới được đưa vào danh sách) và **tiêu chí tối ưu** (dùng để so sánh các ứng viên hợp lệ).

| Tiêu chí | Câu hỏi cần trả lời | Cách xác minh / chỉ số |
|---|---|---|
| **Lưu trú dữ liệu và tuân thủ** | Dữ liệu nào phải nằm trong quốc gia/khu vực nào? Có được chuyển bản sao, log hoặc backup ra ngoài không? | Danh mục dữ liệu, yêu cầu pháp lý và hợp đồng, đánh giá bảo mật, tài liệu theo từng dịch vụ |
| **Độ trễ** | Người dùng, hệ thống đối tác và dịch vụ phụ trợ ở đâu? | Đo thời gian phản hồi thực tế, p95/p99, kiểm thử tải từ các vị trí đại diện |
| **Dịch vụ và tính năng** | Region có dịch vụ, phiên bản, loại instance, tính năng AI/serverless/database cần dùng không? | Danh mục dịch vụ theo Region, hạn mức (quota), loại tài nguyên sẵn có |
| **Độ sẵn sàng và phục hồi** | Cần chống lỗi một AZ hay cả Region? Mục tiêu RTO/RPO là bao nhiêu? | Thiết kế Multi-AZ, kiến trúc DR, thử nghiệm khôi phục và chuyển đổi lưu lượng |
| **Tổng chi phí** | Chi phí tính toán, lưu trữ, truyền dữ liệu, backup và vận hành chênh lệch thế nào? | AWS Pricing Calculator, bảng giá đúng Region, dự báo tải, chi phí egress và liên AZ/liên Region |
| **Kết nối và tích hợp** | Có kết nối với văn phòng, hệ thống tại chỗ, SaaS, đối tác hoặc Region khác không? | Thử nghiệm mạng, kế hoạch VPC, VPN/Direct Connect, kiểm tra đường truyền và băng thông |
| **Năng lực vận hành, bảo mật** | Đội ngũ có thể giám sát, trực sự cố, quản trị quyền truy cập và mã hóa ở Region đó không? | Runbook, IAM, KMS, CloudWatch, CloudTrail, AWS Config và kết quả diễn tập |
| **Yêu cầu tổ chức khác** | Có yêu cầu về phát triển bền vững, hợp đồng, mua sắm hoặc hỗ trợ kỹ thuật không? | Chính sách nội bộ, tài liệu chính thức và các tiêu chí được tổ chức phê duyệt |

### 3.1. Độ trễ cần được đo, không suy từ địa lý

Khoảng cách vật lý chỉ là một tín hiệu ban đầu. Độ trễ thật còn phụ thuộc tuyến mạng của nhà cung cấp Internet, DNS, số lần gọi qua API, độ trễ truy vấn cơ sở dữ liệu và các hệ thống ngoài AWS.

- Thu thập vị trí người dùng và đối tác; tách yêu cầu tương tác thời gian thực khỏi tác vụ chạy nền.
- Kiểm thử từ nhiều mạng và thời điểm; dùng **p95/p99** cùng thời gian đáp ứng đầu cuối thay vì chỉ lấy ping trung bình.
- Đo cả đường đi ứng dụng → database, ứng dụng → đối tác, và tải nội dung từ CloudFront nếu dùng CDN.
- Xác định ngưỡng trải nghiệm chấp nhận được, ví dụ p95 của API quan trọng theo yêu cầu nghiệp vụ; kiểm tra lại sau khi tối ưu cache và kiến trúc.

### 3.2. Tính sẵn sàng: Multi-AZ và Multi-Region giải quyết rủi ro khác nhau

**Multi-AZ** phù hợp để giảm ảnh hưởng của lỗi tại một AZ: các thành phần không trạng thái triển khai ở nhiều AZ, dữ liệu dùng cơ chế HA mà dịch vụ hỗ trợ, kết hợp sao lưu và diễn tập. **Multi-Region** có thể giảm rủi ro cấp Region nhưng đòi hỏi đồng bộ dữ liệu, định tuyến, kiểm thử failover, quản trị khóa và ngân sách lớn hơn.

Hai chỉ số DR cần xác định trước:

- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để khôi phục dịch vụ sau sự cố.
- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa chấp nhận được, tính theo thời gian giữa bản ghi cuối có thể khôi phục và thời điểm sự cố.

Việc tạo một bản sao ở Region khác không tự tạo nên một hệ thống DR hoạt động. Cần kiểm tra độ trễ sao chép, tính nhất quán, quyền truy cập, DNS/routing, hạ tầng ở nơi dự phòng, và thực hiện diễn tập khôi phục.

### 3.3. Đánh giá chi phí toàn vòng đời

Đừng chỉ so giá EC2 hoặc database theo giờ. Tổng chi phí thường gồm:

**Compute + database + storage + request + truyền dữ liệu + backup/replication + quan sát hệ thống + vận hành/DR.**

Giá, đơn vị tính và khả năng hỗ trợ khác nhau theo Region, dịch vụ và thời điểm. Đặc biệt, lưu lượng Internet outbound, liên AZ và liên Region có thể phát sinh phí tùy đường truyền, dịch vụ và cấu hình. Dùng AWS Pricing Calculator cùng dự báo lưu lượng thực tế; so sánh trên cùng một kịch bản tải và cùng yêu cầu độ sẵn sàng.

## 4. Yêu cầu lưu trú dữ liệu: xác định chính xác thứ phải ở đâu

**Data residency** trả lời câu hỏi *dữ liệu được lưu trữ hoặc xử lý tại vị trí địa lý nào*. **Data localization** là yêu cầu cụ thể hơn, có thể bắt buộc một loại dữ liệu phải được lưu hoặc xử lý trong phạm vi lãnh thổ nhất định. **Data sovereignty** liên quan đến quyền tài phán và khả năng kiểm soát pháp lý đối với dữ liệu. Các khái niệm có liên hệ nhưng không thể dùng thay thế nhau.

Ví dụ, một doanh nghiệp muốn cải thiện độ trễ cho khách hàng ở Việt Nam có thể xem xét nhiều Region ứng viên. Tuy nhiên, nếu hợp đồng hoặc quy định áp dụng bắt buộc một loại dữ liệu phải lưu tại lãnh thổ Việt Nam, không thể mặc nhiên coi một Region ở quốc gia lân cận là hợp lệ. Cần đối chiếu yêu cầu cụ thể với vị trí dịch vụ, phương thức triển khai và ý kiến của bộ phận pháp chế/tuân thủ.

**Mã hóa, IAM và việc chọn Region là các biện pháp khác nhau.** Mã hóa bảo vệ tính bí mật của dữ liệu; nó không khiến dữ liệu được lưu bên ngoài lãnh thổ trở thành dữ liệu lưu trong lãnh thổ. Quyền truy cập giới hạn người được thao tác; nó cũng không tự bảo đảm vị trí mọi bản sao dữ liệu.

### 4.1. Phân loại dữ liệu và luồng di chuyển

Trước khi chọn Region, lập danh mục:

| Nhóm dữ liệu | Ví dụ | Câu hỏi kiểm tra vị trí |
|---|---|---|
| Dữ liệu nghiệp vụ chính | Hồ sơ khách hàng, đơn hàng, giao dịch, tệp tải lên | Region nào lưu bản gốc? Dịch vụ có sao chép sang nơi khác không? |
| Dữ liệu vận hành | Log ứng dụng, log truy cập, trace, metric, sự kiện bảo mật | Log được gửi đến CloudWatch, S3, SIEM hay tài khoản tập trung nào? |
| Bản sao và lưu trữ dài hạn | Backup, snapshot, S3 replication, dữ liệu xuất sang kho phân tích | Có chính sách sao chép liên Region, xuất dữ liệu hoặc lưu trữ ở nơi khác không? |
| Dữ liệu tạm và phân phối | Cache, CDN, hàng đợi, tệp tạm, kết quả xử lý | Cache hay cơ chế phân phối có thể đặt dữ liệu ở ngoài phạm vi cho phép không? |
| Metadata và dữ liệu điều khiển | Định danh, cấu hình tài khoản, sự kiện dịch vụ, thông tin hỗ trợ | Dịch vụ đó là Regional hay global; tài liệu dịch vụ nói gì về vị trí metadata? |
| Bản sao do con người tạo | File CSV tải về, dữ liệu hỗ trợ, bản xuất thử nghiệm | Có quy định vị trí laptop, hệ thống phân tích, nhà cung cấp phụ và môi trường test không? |

Phân loại theo mức nhạy cảm (chẳng hạn công khai, nội bộ, dữ liệu cá nhân, dữ liệu chịu ràng buộc đặc biệt), chủ thể dữ liệu, thời hạn lưu, mục đích xử lý và quốc gia/địa bàn được phép. Sau đó vẽ luồng dữ liệu từ điểm nhận vào đến lưu trữ, xử lý, sao lưu, giám sát và xóa bỏ.

### 4.2. Những giả định dễ sai khi dùng AWS

1. **“Tạo tài nguyên ở Region A nghĩa là toàn bộ dữ liệu luôn nằm ở Region A.”** Không đủ cơ sở để kết luận như vậy. Cần xem hành vi từng dịch vụ, đặc biệt dịch vụ global, edge, các tính năng sao chép và kênh hỗ trợ/vận hành.
2. **“RDS Multi-AZ là sao chép sang một Region khác.”** Multi-AZ của RDS hoạt động trong cùng Region; kiến trúc DR liên Region là quyết định riêng.
3. **“S3 tự sao chép sang Region khác để an toàn.”** Sao chép S3 liên Region là tính năng cần cấu hình phù hợp; không nên giả định có hoặc không có bản sao chỉ từ tên bucket. Kiểm tra cả replication, quy trình copy và backup.
4. **“Dùng CloudFront thì dữ liệu vẫn chỉ ở Region gốc.”** CDN có thể cache nội dung tại edge location; phải đánh giá loại nội dung được cache và vị trí được phép phân phối.
5. **“Dùng AWS KMS là đủ đáp ứng lưu trú dữ liệu.”** Khóa KMS và dữ liệu mã hóa có vòng đời/vị trí cần kiểm soát riêng. Tính năng KMS multi-Region keys cũng cần được đánh giá nếu bật.
6. **“Bật chặn Region là đủ tuân thủ.”** Các chính sách theo Region không tự kiểm soát mọi hành vi gọi dịch vụ global hoặc các tác vụ làm dữ liệu di chuyển giữa Region.

### 4.3. Bản gốc, log, backup và DR phải có chung chính sách

Một yêu cầu như “thông tin khách hàng chỉ được lưu tại khu vực X” cần được chuyển thành quy tắc kỹ thuật có thể kiểm chứng:

- Hệ thống chính: EC2/ECS/Lambda, database, S3, EBS, EFS và các dịch vụ tích hợp được đặt tại các Region được phép; kiểm tra **khả năng hỗ trợ thực tế** từng dịch vụ.
- Dữ liệu đi kèm: xác định đích của CloudTrail, CloudWatch Logs, VPC Flow Logs, log truy cập load balancer, kết quả truy vấn, hàng đợi và kho phân tích.
- Sao lưu: kiểm tra AWS Backup, snapshot, S3 replication, database replica và các tác vụ export; không cấu hình đích ngoài phạm vi được phép.
- Phân phối: phân loại nội dung nào có thể đưa lên CloudFront hoặc cache ở biên; kiểm tra tính năng, vị trí xử lý, hợp đồng và kiểm soát cache.
- Khóa và bảo mật: chọn Region và chính sách AWS KMS phù hợp; bảo vệ quyền truy cập bằng IAM, mã hóa khi truyền và khi lưu.
- Vận hành: kiểm soát bản xuất thủ công, môi trường thử nghiệm, hệ thống hỗ trợ, tài khoản phân tích và đơn vị xử lý phụ.

Quyết định về quyền tài phán và tuân thủ phải dựa trên quy định áp dụng, hợp đồng và tài liệu mới nhất của từng dịch vụ AWS; tài liệu kiến trúc không thay thế đánh giá pháp lý.

## 5. Phương án triển khai theo giới hạn địa lý

| Phương án | Nên cân nhắc khi | Ưu điểm | Giới hạn và việc cần kiểm tra |
|---|---|---|---|
| **Một Region, nhiều AZ** | Cần HA cấp AZ; dữ liệu bị giới hạn trong một Region/khu vực | Ít phức tạp hơn, đường đi dữ liệu thường ngắn | Không loại bỏ rủi ro sự cố toàn Region; cần backup và khôi phục đã kiểm thử |
| **Hai Region trong phạm vi được phép** | Cần DR cấp Region và được phép nhân bản dữ liệu giữa các Region đó | Có thể khôi phục khi Region chính ngừng hoạt động | Chi phí tăng; phải quản lý replica, khóa, đồng bộ, chuyển vùng, RTO/RPO |
| **Một Region và phương án DR tại vị trí được phê duyệt khác** | Ràng buộc địa lý hạn chế lựa chọn AWS Region | Cho phép thiết kế theo yêu cầu lưu trú cụ thể | Cần xác nhận tính phù hợp của mô hình tại chỗ/hybrid, phụ thuộc dịch vụ và khả năng thực thi |

**Nguyên tắc lựa chọn:** Phạm vi địa lý được phép là điều kiện loại trừ trước. Chỉ sau đó mới tối ưu độ trễ, độ tin cậy và chi phí. Nếu không Region nào đáp ứng yêu cầu pháp lý bắt buộc, cần thay đổi thiết kế hoặc lựa chọn nền tảng/vị trí triển khai phù hợp; không nên hạ thấp điều kiện tuân thủ để chọn Region gần nhất.

## 6. Quy trình chọn Region có thể áp dụng trong dự án

### Bước 1 — Chốt điều kiện bắt buộc

Xác định loại dữ liệu, quốc gia/khu vực lưu và xử lý được phép, yêu cầu hợp đồng, tiêu chuẩn an toàn, dịch vụ bắt buộc, nhu cầu kết nối, RTO/RPO và ngân sách. Phân biệt yêu cầu có thể thương lượng với yêu cầu buộc phải đáp ứng.

**Đầu ra:** danh sách điều kiện “đạt/không đạt”; Region vi phạm một điều kiện bắt buộc bị loại khỏi danh sách ứng viên.

### Bước 2 — Lập danh sách Region hợp lệ

Với từng ứng viên, kiểm tra danh sách dịch vụ đang hỗ trợ, loại instance, giới hạn quota và các tính năng thực sự cần. Lưu ý: dịch vụ có mặt trong một Region không có nghĩa là mọi tính năng, phiên bản hoặc loại tài nguyên đều sẵn có.

**Đầu ra:** danh sách Region đã qua kiểm tra vị trí dữ liệu và năng lực dịch vụ.

### Bước 3 — Đo thử và ước lượng chi phí

Triển khai một luồng thử tối thiểu hoặc dùng phép đo đại diện, đo p95/p99 ở vị trí người dùng và hệ thống đối tác; ước lượng giá cho cùng mức tải, lượng lưu trữ, băng thông, backup và DR.

**Đầu ra:** bảng so sánh có bằng chứng đo, giả định tải và ngày thu thập.

### Bước 4 — Chấm điểm ứng viên và ghi quyết định

Ví dụ **giả định để minh họa phương pháp**, với hai Region đã được bộ phận tuân thủ xác nhận đều hợp lệ cho loại dữ liệu của dự án. Điểm từ 1 (kém phù hợp) đến 5 (rất phù hợp), không phản ánh đo đạc hay bảng giá thực tế của AWS:

| Yếu tố | Trọng số | Singapore — ap-southeast-1 | Tokyo — ap-northeast-1 |
|---|---:|---:|---:|
| Độ trễ từ nhóm người dùng mục tiêu | 35% | 5 | 3 |
| Tổng chi phí theo tải giả định | 20% | 4 | 5 |
| Dịch vụ và tính năng yêu cầu | 15% | 5 | 5 |
| Khả năng HA và DR theo thiết kế | 20% | 4 | 4 |
| Mức phù hợp với năng lực vận hành | 10% | 5 | 3 |
| **Điểm có trọng số** | **100%** | **4,60/5** | **3,90/5** |

Điểm được tính bằng tổng của **trọng số × điểm từng yếu tố**. Trong ví dụ, Singapore được chọn cho thiết kế thử nghiệm vì điểm cao hơn. **Nếu dự án bắt buộc dữ liệu lưu trong lãnh thổ Việt Nam và hai Region ứng viên đều không đáp ứng yêu cầu đó, cả hai phải bị loại từ Bước 1, bất kể điểm số.**

### Bước 5 — Triển khai guardrail và giám sát

Thiết lập:

- **Cấu hình IaC:** khai báo Region trong Terraform, AWS CloudFormation hoặc pipeline; kiểm tra mã trước khi triển khai.
- **Quản trị tài khoản:** dùng AWS Organizations/SCP để giới hạn thao tác tại các Region không được phê duyệt, nhưng phải thiết kế ngoại lệ cho dịch vụ global và kiểm chứng các thao tác xuyên Region.
- **Kiểm kê liên tục:** dùng AWS Config, CloudTrail, AWS Resource Explorer hoặc công cụ quản trị tài nguyên phù hợp để phát hiện tài nguyên, thay đổi cấu hình và hoạt động ở Region ngoài danh sách.
- **Quản lý đích lưu:** xem xét chính sách bucket S3, đích backup/log, quyền sao chép liên Region và luồng xuất dữ liệu.
- **Giới hạn chi phí:** gắn thẻ tài nguyên, AWS Budgets và cảnh báo chi phí, dự báo dữ liệu truyền liên AZ/liên Region.
- **Kiểm thử vận hành:** chạy bài kiểm tra failover, restore, quyền truy cập, khả năng truy vết, độ trễ và luồng dữ liệu sau thay đổi.

Với AWS Organizations, điều kiện **aws:RequestedRegion** hữu ích để giới hạn endpoint Region của nhiều thao tác API, nhưng không bảo đảm rằng thao tác đó không tác động đến dữ liệu ở Region khác. Ví dụ, một thao tác cấu hình sao chép có thể dẫn đến dữ liệu được chuyển ra ngoài Region. Vì vậy, kết hợp SCP với kiểm tra hành vi theo dịch vụ, chính sách tài nguyên và giám sát.

### Bước 6 — Rà soát định kỳ

Khi thêm dịch vụ mới, nguồn dữ liệu mới, chức năng CDN, tính năng replication hoặc thị trường khách hàng mới, cập nhật sơ đồ luồng dữ liệu và quyết định Region. Kiểm chứng lại thông tin khi AWS thay đổi danh mục dịch vụ, giá hoặc tính năng theo Region.

## 7. Ví dụ kiểm tra bằng AWS CLI

Các lệnh dưới đây dùng để **hỗ trợ kiểm kê**, không tự tạo thành bằng chứng tuân thủ đầy đủ. Chạy với quyền đọc phù hợp, tài khoản/profile đúng và cấu hình AWS CLI đã được thiết lập.

~~~bash
# Xem các Region mà tài khoản có thể nhận diện và trạng thái opt-in.
aws ec2 describe-regions --all-regions \
  --query 'Regions[].[RegionName,OptInStatus]' \
  --output table

# Xem Region của một S3 bucket cụ thể.
aws s3api get-bucket-location \
  --bucket your-example-bucket

# Xem cấu hình Multi-AZ của RDS ở Region đang đánh giá.
aws rds describe-db-instances \
  --region ap-southeast-1 \
  --query 'DBInstances[].[DBInstanceIdentifier,AvailabilityZone,MultiAZ]' \
  --output table
~~~

**Đọc kết quả đúng cách:**

- Lệnh liệt kê Region chỉ cung cấp thông tin Region/opt-in; không chứng minh mọi dịch vụ sẵn có hoặc dự án đã được phép lưu dữ liệu tại Region đó.
- Giá trị **LocationConstraint** của S3 bucket có trường hợp đặc biệt: giá trị rỗng/null tương ứng Region **us-east-1** (US East – N. Virginia). Kiểm tra thêm cấu hình sao chép, backup và đích xuất dữ liệu.
- Trường **MultiAZ** của RDS cho biết tùy chọn Multi-AZ của DB instance, không phải trạng thái DR liên Region hoặc kiểm thử khôi phục thành công. Với kiến trúc database khác, dùng API kiểm kê tương ứng.
- Với tài khoản có nhiều Region, cần lặp kiểm kê theo các Region liên quan và gộp kết quả từ mọi tài khoản AWS trong phạm vi quản trị.

## 8. Bài tập tình huống

**Tình huống A — Nền tảng bán hàng:** Khách hàng chủ yếu truy cập từ một nhóm quốc gia Đông Nam Á. Nhóm phát triển dùng API, database, S3 cho ảnh sản phẩm, CloudFront và job phân tích hằng ngày. Không có yêu cầu pháp lý bắt buộc dữ liệu phải lưu tại một quốc gia duy nhất, nhưng hợp đồng giới hạn một số luồng dữ liệu ra ngoài các quốc gia được phê duyệt.

**Câu hỏi:** Nên kiểm tra gì trước khi chốt Region và bật CloudFront?

**Gợi ý xử lý:** Phân loại hồ sơ khách hàng và ảnh có dữ liệu nhạy cảm hay không; xác nhận danh sách quốc gia/Region được phép; đo độ trễ từ người dùng; kiểm tra khả năng cung cấp các dịch vụ; kiểm tra nơi lưu log, cache, dữ liệu phân tích, backup; thiết kế Multi-AZ; dự báo chi phí; ghi lại quyết định và làm thử kiểm tra vận hành. CloudFront chỉ được cấu hình cho dữ liệu và phạm vi phân phối đã được phê duyệt.

**Tình huống B — Hệ thống có dữ liệu bị giới hạn lãnh thổ:** Một hệ thống xử lý hồ sơ có điều khoản bắt buộc lưu bản gốc, snapshot và log chứa dữ liệu nhạy cảm trong lãnh thổ quốc gia X. Region A có độ trễ thấp nhất nhưng nằm ngoài quốc gia X. Region B gần hơn về mặt pháp lý nhưng không hỗ trợ tính năng database bắt buộc.

**Câu hỏi:** Có nên chọn Region A vì nhanh hoặc Region B vì đúng vị trí?

**Gợi ý xử lý:** Không được chọn Region A nếu vi phạm điều kiện bắt buộc. Region B chỉ là ứng viên khi có giải pháp kỹ thuật đáp ứng đầy đủ tính năng và ràng buộc dữ liệu; nếu chưa có, cần tìm kiến trúc/dịch vụ/vị trí khác được phê duyệt. Sau khi đáp ứng điều kiện bắt buộc mới tiếp tục tối ưu hiệu năng và chi phí.

## 9. Checklist trước khi phê duyệt Region

- [ ] Đã xác định dữ liệu nào cần lưu, xử lý, sao lưu và xóa tại vị trí nào.
- [ ] Đã có kết luận của người phụ trách pháp chế/tuân thủ về Region và luồng dữ liệu được phép.
- [ ] Đã kiểm tra dịch vụ, tính năng, loại instance và quota trong từng Region ứng viên.
- [ ] Đã đo hoặc lập kế hoạch đo độ trễ người dùng, API, database và hệ thống đối tác.
- [ ] Đã chọn kiến trúc Multi-AZ, xác định RTO/RPO và cách diễn tập khôi phục.
- [ ] Đã kiểm tra nơi lưu S3, database, snapshot, backup, log, cache, CDN và kết quả phân tích.
- [ ] Đã xác định cơ chế bảo vệ IAM/KMS, chính sách Region và cảnh báo cấu hình sai.
- [ ] Đã dự toán tổng chi phí, bao gồm truyền dữ liệu, backup và DR.
- [ ] Đã có tài liệu quyết định Region, người phê duyệt, giả định và lịch rà soát.

## 10. Ghi nhớ

Chọn Region là bài toán **điều kiện bắt buộc trước, tối ưu sau**. Việc đánh giá đúng giúp cân bằng trải nghiệm người dùng với an toàn, khả năng giám sát, phục hồi và chi phí. Region quyết định nơi đặt phần lớn tài nguyên Regional, nhưng yêu cầu lưu trú dữ liệu chỉ có thể được xác nhận sau khi xem **toàn bộ vòng đời dữ liệu**, bao gồm cache, log, backup, replication, dữ liệu quản trị và các dịch vụ global.

### Nguồn AWS nên đối chiếu khi triển khai thực tế

- [AWS Global Infrastructure](https://aws.amazon.com/about-aws/global-infrastructure/) — bản đồ Region, AZ và hạ tầng toàn cầu.
- [AWS Services by Region](https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/) — dịch vụ hỗ trợ theo Region.
- [AWS Data Privacy](https://aws.amazon.com/compliance/data-privacy/) — tài liệu AWS về bảo vệ dữ liệu và các lựa chọn của khách hàng.
- [AWS IAM: aws:RequestedRegion](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html#condition-keys-requestedregion) — ý nghĩa và giới hạn của điều kiện Region trong chính sách.
- [AWS Pricing Calculator](https://calculator.aws/) — lập dự toán trước khi triển khai.

# Disaster recovery là gì? Thiết kế và kiểm chứng khả năng khôi phục hệ thống sau thảm họa

**Disaster recovery (DR, khôi phục sau thảm họa)** là tập hợp chiến lược, con người, quy trình, hạ tầng và phương pháp kiểm thử nhằm khôi phục hệ thống công nghệ, dữ liệu và những năng lực kỹ thuật thiết yếu sau một sự kiện gián đoạn nghiêm trọng. DR trả lời câu hỏi: **nếu những thành phần đang vận hành bị mất, không còn tin cậy hoặc không thể truy cập, tổ chức sẽ phục hồi dịch vụ ở đâu, bằng dữ liệu nào, theo thứ tự nào và làm sao biết việc phục hồi đã đạt yêu cầu?**

Trong module **SECURITY_SECURITY_ASSURANCE**, chủ đề thuộc chương **Disaster recovery**. Mục tiêu của module là xây dựng cách đánh giá **có bằng chứng** rằng hệ thống đáp ứng các mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và security controls đến kiểm thử, audit và khắc phục phát hiện; đồng thời tổ chức chương trình security assurance liên tục trong phát triển và vận hành. Vì vậy, một kế hoạch DR không được coi là đã hiệu quả chỉ vì đã được viết hoặc vì hệ thống sao lưu báo “thành công”. Cần **khôi phục thử**, đo thời gian và mức mất dữ liệu, xác minh dữ liệu có thể sử dụng, bảo đảm trạng thái sau khôi phục an toàn và giữ bằng chứng cho kết luận.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích DR là gì, khi nào cần kích hoạt và phân biệt DR với business continuity, backup, high availability và incident response.
2. Xác định ranh giới lỗi, tài sản phụ thuộc, tình huống thảm họa và yêu cầu phục hồi từ business impact analysis (BIA).
3. Hiểu đúng **Recovery Time Objective (RTO)**, **Recovery Point Objective (RPO)**, thời gian gián đoạn tối đa có thể chịu đựng và các phép đo thực tế.
4. So sánh các chiến lược backup-and-restore, pilot light, warm standby, hot standby, active-passive và active-active theo chi phí, độ phức tạp và mức rủi ro.
5. Thiết kế kiến trúc khôi phục bao gồm dữ liệu, ứng dụng, mạng, danh tính, khóa, hạ tầng, nhà cung cấp và kênh điều hành.
6. Viết runbook phục hồi với điều kiện kích hoạt, trách nhiệm, trình tự kỹ thuật, kiểm tra an toàn và tiêu chí bàn giao.
7. Lập kế hoạch diễn tập, đo RTO/RPO đạt được, xác minh tính toàn vẹn dữ liệu và đánh giá hiệu lực controls bằng bằng chứng.
8. Nhận diện rủi ro phục hồi sau tấn công mạng, đặc biệt khi bản sao lưu hoặc môi trường dự phòng có thể bị ảnh hưởng.

## 2. Khái niệm cốt lõi: DR bảo vệ điều gì?

Một dịch vụ kinh doanh hiếm khi chỉ là một máy chủ. Ví dụ, ứng dụng thanh toán có thể cần API, database, message broker, kho khóa, hệ thống định danh, DNS, kết nối đối tác và hạ tầng quan sát. Phục hồi riêng máy ảo mà database vẫn không thể giải mã, DNS chưa chuyển hoặc credential kết nối đối tác không sử dụng được chưa phải là **khôi phục dịch vụ đầu cuối**.

DR thường bảo vệ bốn nhóm năng lực:

- **Khả năng phục hồi hệ thống:** có hạ tầng, tài nguyên và quy trình để tạo lại thành phần cần thiết.
- **Khả năng phục hồi dữ liệu:** có điểm khôi phục phù hợp, dữ liệu nhất quán và không bị mất quá ngưỡng chấp nhận.
- **Khả năng phục hồi vận hành:** đội có thẩm quyền có thể ra quyết định, truy cập hệ thống dự phòng và thực hiện runbook khi hạ tầng chính gặp lỗi.
- **Khả năng phục hồi an toàn:** không vô tình tái triển khai mã độc, cấu hình yếu, credential bị chiếm hoặc dữ liệu bị sửa trái phép.

**DR không đồng nghĩa hệ thống phải luôn hoạt động không gián đoạn.** Một chiến lược có thể chấp nhận tạm ngừng dịch vụ để đổi lấy chi phí thấp hơn, miễn mức gián đoạn và mất dữ liệu đáp ứng yêu cầu đã phê duyệt.

### 2.1. Phân biệt các lĩnh vực liên quan

| Khái niệm | Mục tiêu chính | Ví dụ | Giới hạn cần hiểu |
|---|---|---|---|
| **Disaster recovery (DR)** | Phục hồi hệ thống, dữ liệu và dịch vụ sau gián đoạn lớn | Khôi phục dịch vụ tại vùng dự phòng khi vùng chính không dùng được | Phải chứng minh khả năng vận hành đầu cuối và bảo mật sau phục hồi |
| **Business continuity (BC)** | Duy trì hoạt động nghiệp vụ thiết yếu trong và sau gián đoạn | Tạm chuyển sang quy trình thủ công, kênh giao dịch thay thế | Bao gồm con người, nhà cung cấp, địa điểm, pháp lý và công nghệ; phạm vi rộng hơn DR |
| **Backup** | Tạo và lưu bản sao dữ liệu/cấu hình tại một thời điểm hoặc theo chu kỳ | Snapshot, backup database, bản sao object | Có backup chưa chắc restore được hoặc đạt RTO/RPO |
| **High availability (HA)** | Giảm gián đoạn khi một số thành phần lỗi | Nhiều replica, failover node trong một vùng | Không nhất thiết chịu được mất cả region, hỏng dữ liệu logic hoặc ransomware |
| **Fault tolerance** | Tiếp tục hoạt động dù có một số lỗi được thiết kế trước | Đa bản sao có cơ chế xử lý lỗi | Có giới hạn failure model; lỗi chung vẫn có thể phá vỡ |
| **Incident response (IR)** | Phát hiện, phân tích, khống chế và xử lý sự cố an ninh | Thu hồi credential, cô lập workload, điều tra | Có thể phối hợp DR; phục hồi nhanh không đồng nghĩa nguồn tấn công đã được loại bỏ |
| **Cyber recovery** | Khôi phục sau sự cố mạng, có bước xác minh môi trường và dữ liệu sạch | Restore trong clean room rồi mới mở lại truy cập | Đòi hỏi thêm kiểm tra tính tin cậy của backup, identity và artifact |

Ví dụ: một cơ sở dữ liệu có replication đồng bộ giữa hai node trong cùng cụm có thể giúp HA đối với hỏng một node. Nhưng nếu một lệnh xóa dữ liệu hợp lệ bị thực thi sai, lệnh đó có thể được replicate đến cả hai node. Khi đó **khả năng phục hồi điểm dữ liệu cũ** vẫn phụ thuộc vào backup, point-in-time recovery hoặc các kiểm soát khác.

### 2.2. Khi nào một sự kiện được xem là “disaster”?

Không có định nghĩa kỹ thuật duy nhất cho mọi tổ chức. Một sự kiện nên được xử lý theo DR khi vượt ngưỡng mà hoạt động sửa lỗi thông thường hoặc HA không còn đáp ứng yêu cầu nghiệp vụ, và cần **kích hoạt chế độ phục hồi được chuẩn bị trước**.

Các tình huống tham khảo:

- Mất toàn bộ data center hoặc một vùng cloud có workload quan trọng.
- Hỏng lưu trữ khiến dữ liệu chính không sử dụng được.
- Sự cố quy mô lớn ở mạng, DNS, hệ thống định danh hoặc hệ thống quản lý khóa.
- Mất khả năng điều khiển nền tảng triển khai và phải khởi tạo hạ tầng tại nơi khác.
- Ransomware hoặc hành vi phá hoại khiến hệ thống hoặc backup thông thường không còn đáng tin.
- Lỗi thay đổi cấu hình dẫn đến việc hệ thống phải khôi phục từ một mốc trạng thái an toàn.
- Nhà cung cấp hoặc kết nối thiết yếu bị gián đoạn dài hơn mức chịu đựng.

**Kích hoạt DR là quyết định quản trị rủi ro**, cần có tiêu chí và người có thẩm quyền, không chỉ là một lệnh tự động khởi chạy ở mọi trường hợp lỗi nhỏ.

## 3. Từ rủi ro đến kịch bản khôi phục

Muốn đánh giá DR có hiệu lực, trước hết phải xác định **mất cái gì**, **trong bao lâu** và **trong hoàn cảnh nào**. Thiết kế dựa trên một “thảm họa chung chung” dễ bỏ sót phụ thuộc dùng chung và hạn chế khi diễn tập.

### 3.1. Ranh giới lỗi (failure domain)

Một failure domain là tập thành phần có thể cùng bị ảnh hưởng bởi một sự kiện. Phạm vi này thay đổi theo nhà cung cấp và cách triển khai:

| Failure domain | Sự cố ví dụ | Câu hỏi DR |
|---|---|---|
| Tiến trình/container | Crash, hết bộ nhớ, lỗi bản cập nhật | Replica hoặc rollback có đủ để khôi phục? |
| Node/máy chủ | Hỏng phần cứng, lỗi host OS | Replica, storage và scheduler có nằm trên node độc lập? |
| Availability zone/data hall | Mất điện/kết nối cục bộ | Dữ liệu và dịch vụ có thể hoạt động ở zone khác? |
| Region/data center | Mất hạ tầng nhiều zone cùng một vùng | Có vùng độc lập đủ điều kiện phục hồi, dữ liệu và routing? |
| Account/tenant/quyền quản trị | Lockout, lỗi IAM policy, credential bị chiếm | Môi trường DR có phụ thuộc cùng control plane và identity? |
| Mạng và DNS | Tuyến mạng, resolver hoặc cấu hình DNS lỗi | Có đường chuyển traffic và kiểm chứng từ phía người dùng? |
| Dữ liệu logic | Xóa nhầm, corruption, replicate sai dữ liệu | Có điểm restore trước lỗi và quy trình đối soát? |
| KMS/secret manager | Mất hoặc khóa truy cập key/secret | Backup đã mã hóa có còn giải mã được ở nơi phục hồi? |
| Chuỗi cung ứng | Artifact bị thay thế, registry hoặc CI/CD lỗi | Có image/config tin cậy để tái tạo hệ thống? |
| Con người/nhà cung cấp | Không thể liên hệ đội trực hoặc đối tác ngừng dịch vụ | Có người thay thế, kênh ngoài hệ thống chính, cam kết hỗ trợ? |

**Đa vùng không tự động bảo đảm độc lập.** Hai vùng có thể cùng phụ thuộc vào một account, cùng cơ chế cấp quyền, secret, CI/CD, DNS, nơi chứa Terraform state hoặc đường kết nối. DR phải vẽ được các điểm phụ thuộc chung đó.

### 3.2. Threat model cho DR

Tài sản quan trọng gồm: dữ liệu chính, bản sao và log giao dịch, backup catalog, quyền restore, snapshot, hạ tầng dự phòng, hạ tầng quản lý khóa, artifact tin cậy, DNS và runbook.

Các tác nhân và rủi ro cần xét:

- Lỗi phần cứng/hạ tầng, mất điện, thiên tai hoặc sự cố nhà cung cấp.
- Lỗi thao tác quản trị, triển khai sai hoặc xóa nhầm.
- Malware/ransomware phá dữ liệu, backup, catalog và thông tin đăng nhập.
- Người có quyền cao xóa bản sao, thay retention hoặc vô hiệu hóa replication.
- Corruption âm thầm được nhân bản sang DR site trước khi phát hiện.
- Thiếu dung lượng hoặc quota tại môi trường dự phòng.
- Runbook phụ thuộc một công cụ hoặc một người không còn sẵn.
- Hỏng nguồn bằng chứng khiến đội không biết bản sao nào đủ an toàn để khôi phục.

Một chiến lược đáp ứng mất node có thể không đáp ứng ransomware. Do đó, **test phải gắn với failure scenario cụ thể**.

### 3.3. Xác định những phụ thuộc cần khôi phục

~~~mermaid
flowchart TB
    BIZ["Dịch vụ nghiệp vụ: thanh toán"] --> API["API/worker"]
    BIZ --> DB["Database / transaction log"]
    BIZ --> MQ["Message broker"]
    API --> ID["Identity / workload credentials"]
    API --> SECRET["KMS / secret manager"]
    API --> NETWORK["DNS / network / ingress"]
    DB --> BACKUP["Backup + restore catalog"]
    API --> IMAGE["Image / IaC / artifact registry"]
    MQ --> STORAGE["Persistent storage"]
    ID --> OPS["Quyền truy cập khẩn cấp"]
    BACKUP --> OPS
    NETWORK --> EXT["Đối tác và khách hàng"]
    DB --> VERIFY["Đối soát dữ liệu"]
    MQ --> VERIFY
~~~

Sơ đồ là ví dụ kiến trúc phụ thuộc. Trong thực tế, phải kiểm kê chính xác sự phụ thuộc của từng hệ thống. Nếu database khôi phục nhưng message broker mang lại những message cũ hoặc bị mất, ứng dụng có thể ghi trùng giao dịch. Bài toán DR cần xét **nhất quán giữa nhiều thành phần**, không chỉ mỗi database độc lập.

## 4. BIA: xác định mục tiêu phục hồi từ tác động nghiệp vụ

**Business Impact Analysis (BIA)** đánh giá hậu quả khi một hoạt động bị gián đoạn, mức ảnh hưởng tăng theo thời gian và những điều kiện tối thiểu để tiếp tục hoạt động. Kết quả BIA giúp nhóm nghiệp vụ và kỹ thuật thỏa thuận yêu cầu phục hồi.

### 4.1. RTO, RPO và các ngưỡng liên quan

**Recovery Time Objective (RTO)** là thời gian mục tiêu tối đa được phép để khôi phục một dịch vụ hoặc năng lực sau điểm bắt đầu gián đoạn đã định nghĩa trong kế hoạch. RTO là **mục tiêu**, không phải thời gian một phép thử đã đạt.

**Recovery Point Objective (RPO)** là mức mất dữ liệu theo thời gian mà nghiệp vụ chấp nhận được so với điểm xảy ra gián đoạn. RPO 15 phút có nghĩa cơ chế khôi phục phải đưa hệ thống về điểm dữ liệu đủ mới để mức mất dữ liệu không quá khoảng 15 phút trong failure model đã thỏa thuận.

**Maximum Tolerable Period of Disruption (MTPD/MTD)** là thời gian gián đoạn tối đa mà hoạt động nghiệp vụ có thể chịu đựng trước khi tác động trở nên không chấp nhận được theo định nghĩa BIA. RTO thường được xác định bên trong giới hạn đó, chừa thời gian cho việc khôi phục vận hành nghiệp vụ, nhưng không nên xem các ngưỡng này là một phép tính cứng trong mọi phương pháp.

**Minimum Business Continuity Objective (MBCO)** mô tả mức sản phẩm/dịch vụ tối thiểu mà hoạt động nghiệp vụ cần duy trì hoặc sớm khôi phục, ví dụ xử lý được giao dịch thiết yếu thay vì đủ mọi tính năng.

### 4.2. So sánh với số đo thực tế

| Khái niệm | Loại | Ví dụ giả định |
|---|---|---|
| RTO | Mục tiêu thời gian dịch vụ được phục hồi | Tối đa 2 giờ |
| RPO | Mục tiêu mức mất dữ liệu | Tối đa 15 phút |
| MTPD/MTD | Giới hạn chịu đựng về gián đoạn nghiệp vụ | Tối đa 4 giờ |
| Achieved Recovery Time | Thời gian đo trong diễn tập/sự cố, theo mốc được thống nhất | 93 phút |
| Achieved Recovery Point Lag | Độ lùi dữ liệu từ lúc gián đoạn đến điểm khôi phục nhất quán mới nhất | 9 phút |
| Functional recovery | Xác minh dịch vụ đã đáp ứng tiêu chí phục hồi đã định | API, đối soát và kết nối hoạt động |
| Security recovery | Xác minh control bảo mật quan trọng ở môi trường phục hồi | IAM, logging, monitoring, KMS và dữ liệu sạch |

Trong ví dụ, **93 phút đáp ứng RTO 120 phút** và **9 phút đáp ứng RPO 15 phút**, nếu phép đo bao gồm đúng phạm vi dịch vụ và kịch bản đã thỏa thuận. Nếu mới phục hồi database mà API chưa dùng được thì không được kết luận RTO của dịch vụ đã đạt.

### 4.3. Cách đo tránh sai lệch

Một mô hình đo dễ kiểm tra:

- **Disruption start (T0):** mốc bắt đầu gián đoạn theo định nghĩa của mục tiêu.
- **Recovery verified (T1):** mốc dịch vụ đáp ứng tiêu chí khôi phục đã phê duyệt.
- **Actual recovery duration = T1 − T0.**
- **Last verified consistent recovery point (Tdata):** thời điểm dữ liệu mới nhất được khôi phục và chứng minh nhất quán theo phạm vi.
- **Achieved recovery point lag = T0 − Tdata**, nếu Tdata trước T0.

Với sự cố thật, có thể không xác định chính xác T0 và chỉ biết **earliest observed disruption**. Khi đó phải nêu giới hạn. Đừng bắt đầu đồng hồ RTO ở lúc người vận hành nhấn nút failover nếu thỏa thuận nghiệp vụ đo từ lúc dịch vụ mất.

RPO chỉ thể hiện độ mới của dữ liệu theo thời gian. Khôi phục một snapshot **corrupt** dù chỉ cũ 2 phút vẫn không phải đạt yêu cầu phục hồi đúng nghĩa.

### 4.4. Ví dụ BIA theo dịch vụ

| Dịch vụ | Tác động chính khi gián đoạn | RTO ví dụ | RPO ví dụ | Điều kiện khôi phục tối thiểu |
|---|---|---|---|---|
| Thanh toán trực tuyến | Không nhận hoặc xác nhận giao dịch | 1 giờ | 5 phút | Xử lý an toàn, đối soát giao dịch, tránh ghi trùng |
| Trang thông tin sản phẩm | Giảm khả năng xem nội dung | 12 giờ | 24 giờ | Nội dung hợp lệ, truy cập công khai |
| Hệ thống phân tích nội bộ | Chậm báo cáo | 24 giờ | 12 giờ | Truy xuất dữ liệu đủ chính xác cho kỳ phân tích |
| Quản lý định danh nội bộ | Người dùng không thể đăng nhập dịch vụ quan trọng | 2 giờ | Theo tính chất dữ liệu danh tính | Khôi phục đăng nhập và các quyền thiết yếu, không mở rộng đặc quyền |

Các số liệu chỉ để minh họa cách liên kết mục tiêu với tác động nghiệp vụ, **không phải chuẩn chung**. RTO/RPO phải do owner nghiệp vụ và các bên có trách nhiệm phê duyệt dựa trên BIA, nghĩa vụ pháp lý và chi phí thực thi.

### 4.5. Tránh mục tiêu không khả thi

Yêu cầu “RTO = 0, RPO = 0” cần được làm rõ. **RPO bằng 0** đòi hỏi thiết kế và ngữ nghĩa xác nhận ghi phù hợp để dữ liệu đã được chấp nhận không bị mất trong failure model; replication đồng bộ vẫn có giới hạn, ví dụ lỗi logic lan truyền hoặc lỗi chung. **RTO gần bằng 0** thường đòi hỏi active-active/HA cùng điều kiện vận hành và routing rất nghiêm ngặt. Không có kiến trúc nào mặc định đáp ứng mọi dạng thảm họa.

Một mục tiêu khả thi phải có **scenario, scope, số đo, phương pháp kiểm chứng và ngân sách**.

## 5. Chiến lược khôi phục phổ biến

Không có một giải pháp DR tốt nhất cho mọi ứng dụng. Tùy dữ liệu, nghiệp vụ, failure domain và mục tiêu, có thể kết hợp nhiều kỹ thuật.

| Chiến lược | Mô tả | RTO/RPO tương đối | Chi phí/độ phức tạp | Rủi ro cần chú ý |
|---|---|---|---|---|
| **Backup and restore** | Khởi tạo lại hạ tầng rồi khôi phục dữ liệu | RTO thường dài hơn; RPO theo tần suất và chất lượng backup | Tương đối thấp khi vận hành thường xuyên | Restore chậm, thiếu hạ tầng, backup không dùng được |
| **Pilot light** | Giữ một số thành phần dữ liệu/cốt lõi ở site dự phòng, mở rộng khi cần | Có thể nhanh hơn restore từ đầu | Trung bình | Thiếu capacity/quota, cấu hình và phụ thuộc chưa sẵn |
| **Warm standby** | Chạy môi trường dự phòng quy mô nhỏ, sẵn sàng mở rộng | Thường giảm RTO nếu failover thành công | Cao hơn pilot light | Drift, quá tải khi chuyển traffic, dữ liệu trễ |
| **Hot standby / active-passive** | Môi trường dự phòng gần đầy đủ, thường không phục vụ traffic chính | Có thể rút ngắn RTO đáng kể | Cao | Cấu hình standby không được diễn tập, failback phức tạp |
| **Active-active** | Nhiều môi trường đồng thời phục vụ và chia tải | Có thể giảm thời gian gián đoạn cho failure model phù hợp | Rất cao; xử lý dữ liệu phân tán phức tạp | Split brain, consistency, xung đột ghi, chuyển traffic sai |
| **Isolated cyber recovery** | Bản sao và công cụ phục hồi tách quyền, có bước kiểm tra “clean” | Có thể tăng thời gian phục hồi để bảo đảm an toàn | Tùy quy mô và yêu cầu cô lập | Mất key/trust, phục hồi vào trạng thái vẫn bị nhiễm |

**Không gán số giờ/phút cố định cho từng chiến lược.** Các kết quả phụ thuộc dữ liệu, độ phức tạp, network, quota, đội thực hiện và các phép kiểm sau phục hồi.

### 5.1. Backup and restore

Mô hình cơ bản là lưu backup độc lập, dựng lại hạ tầng tin cậy, phục hồi dữ liệu và kiểm thử chức năng. Phù hợp khi nghiệp vụ chấp nhận ngừng dịch vụ trong một khoảng đáng kể.

Phải kiểm chứng:

- Backup được tạo đúng kỳ, bao gồm dữ liệu, metadata, schema và log cần thiết.
- Backup catalog cho phép tìm đúng điểm restore và phụ thuộc.
- Dữ liệu mã hóa có khóa giải mã sẵn ở nơi phục hồi.
- Quy trình tạo lại hạ tầng/ứng dụng có artifact tin cậy.
- Restore có đủ bandwidth, IOPS, quota và nhân sự.
- Dữ liệu nhất quán, ứng dụng dùng được và quyền được kiểm tra lại.

Một bản sao lưu “success” chỉ xác nhận công việc **tạo bản sao theo cách sản phẩm định nghĩa**. Nó chưa chứng minh restore thành công hoặc bảo đảm RPO.

### 5.2. Replication

Replication chuyển thay đổi giữa các bản sao. **Synchronous replication** thường yêu cầu nhiều bên xác nhận trước khi ghi được coi là hoàn tất, có thể ảnh hưởng latency và availability. **Asynchronous replication** thường giảm ràng buộc latency nhưng có thể trễ dữ liệu.

Cả hai cần xét:

- Điều gì được xác nhận là **durable** và từ thời điểm nào.
- Giới hạn khi mất network hoặc mất một site.
- Tính nhất quán giữa database và message broker.
- Khả năng phát hiện replica bị tụt, corruption hoặc quyền bị thay.
- Cơ chế bầu chọn leader, chống split brain và đảm bảo chỉ một writer khi yêu cầu.

**Replication không thay thế backup có khả năng phục hồi điểm cũ.** Sai lệnh xóa, ransomware hoặc logic corruption có thể lan nhanh tới replica.

### 5.3. Chọn chiến lược theo mục tiêu

Một cách đưa ra quyết định:

1. BIA xác định tác động, RTO, RPO và MBCO.
2. Threat model chỉ ra failure domains phải chịu được.
3. Kiến trúc sư lập phương án với phụ thuộc và chi phí dự kiến.
4. Đội an ninh kiểm tra identity, encryption, backup immutability, nguồn artifact và log.
5. Đội vận hành mô phỏng và đo thời gian thực tế.
6. Owner nghiệp vụ chấp nhận hoặc yêu cầu điều chỉnh nếu kết quả chưa đáp ứng.
7. Kết quả được ghi vào control register và kế hoạch kiểm tra lại.

## 6. Kiến trúc DR: hạ tầng, dữ liệu và quyền phụ thuộc

### 6.1. Kiến trúc tham khảo

~~~mermaid
flowchart LR
    CLIENT["Client / đối tác"] --> ROUTE["DNS / traffic management"]
    ROUTE --> PRIMARY["Primary: app + DB + MQ"]
    ROUTE -. "Chuyển khi được phê duyệt" .-> RECOVERY["Recovery: app + DB + MQ"]
    PRIMARY --> BKS["Backup / journal / recovery points"]
    BKS --> VAULT["Kho backup tách quyền + retention"]
    VAULT --> RECOVERY
    PRIMARY -. "Replication theo chính sách" .-> RECOVERY
    CTRL["Control: IAM, KMS, secrets, IaC"] --> PRIMARY
    CTRL --> RECOVERY
    MON["Monitoring / audit độc lập"] --> PRIMARY
    MON --> RECOVERY
    OPS["DR commander + runbook"] --> ROUTE
    OPS --> RECOVERY
~~~

Sơ đồ chỉ để minh họa; thiết kế thật cần phân tích nguy cơ **CTRL là điểm lỗi chung**. Nếu một danh tính quản trị hoặc key dùng chung đã bị chiếm, attacker có thể tác động cả primary lẫn recovery. Với rủi ro cao, cần cơ chế tách quyền, tài khoản khẩn cấp và sao lưu/khóa thích hợp.

### 6.2. Danh mục thành phần phải sẵn sàng

| Thành phần | Điều kiện chuẩn bị | Phép kiểm assurance |
|---|---|---|
| **Compute/capacity** | Có quota, vùng và năng lực mở rộng đủ | Khởi tạo workload thật trong diễn tập, đo throughput |
| **Network/route** | Subnet, firewall, DNS, certificate và đường client | Kiểm tra truy cập từ vị trí người dùng/đối tác |
| **IAM/identity** | Đường đăng nhập và quyền khẩn cấp có thể dùng độc lập khi cần | Test break-glass, test quyền được phép/bị từ chối |
| **KMS/secrets** | Khóa và bí mật cần restore khả dụng, phân quyền đúng | Restore và giải mã thử, kiểm tra audit quyền |
| **Application artifacts** | Image, package, IaC/config tin cậy, pin version/digest | Rebuild hoặc deploy từ artifact được phê duyệt |
| **Database/storage** | Restore point nhất quán, đủ capacity và performance | Restore, integrity check, business invariants |
| **Messaging/event stream** | Xác định offset, duplicate, replay và thứ tự | End-to-end test, kiểm tra idempotency |
| **External dependencies** | Đối tác/third-party có phương án chuyển endpoint hoặc degraded mode | Test hợp đồng kỹ thuật, mocks khi không thể gọi thật |
| **Monitoring/audit** | Truy cập được log, alert, trace và health khi site chính mất | Synthetic event và kiểm tra alert tại nơi phục hồi |
| **Runbook/communication** | Có owner, số liên hệ ngoài hạ tầng chính, quyền kích hoạt | Tabletop và thử quy trình giao tiếp |

### 6.3. Tại sao phải giữ IaC và cấu hình đáng tin?

Khi hạ tầng chính mất, việc dựng lại từ “trí nhớ đội vận hành” khó tái lập và dễ sai cấu hình. Infrastructure as Code (IaC), template, policy-as-code và deployment manifests giúp xác định trạng thái mong muốn. Nhưng vẫn cần kiểm soát:

- Nguồn mã, phiên bản, chữ ký/attestation nếu có và quyền thay đổi.
- Backend state, secret trong state và khả năng truy cập khi primary lỗi.
- Cấu hình môi trường dự phòng không bị drift so với baseline.
- Quota, region/zone availability và phiên bản sản phẩm được hỗ trợ.
- Quyền CI/CD và build artifact khi hệ thống cấp token thông thường không sẵn có.

Một repository có file Terraform chưa đủ chứng minh hạ tầng DR có thể dựng. Cần **khởi tạo thử và kiểm chứng sau triển khai** trong phạm vi phù hợp.

## 7. Backup an toàn: điều kiện cần của khôi phục đáng tin

### 7.1. Thiết kế chính sách sao lưu

Một backup policy phải nêu:

- Phạm vi dữ liệu: database, object, config, metadata, encryption key dependency, transaction log.
- Loại và chu kỳ: full, incremental, differential, snapshot, continuous log backup hoặc PITR.
- Thời hạn giữ, bản sao ở nơi độc lập và giới hạn về dữ liệu.
- Quyền tạo/xem/restore/xóa backup; separation of duties và audit.
- Bảo vệ confidentiality/integrity: encryption, checksum/signature nếu phù hợp, immutable/offline copy.
- Kiểm tra định kỳ khả năng restore và mức mất dữ liệu đã đo.
- Quy trình xử lý backup bị corruption, không giải mã được hoặc bị nghi có mã độc.

**Quy tắc 3-2-1** (nhiều bản sao, loại phương tiện khác nhau, một bản ngoài nơi chính) có thể là gợi ý tư duy về phân tán rủi ro. Không nên dùng số đếm đó như bằng chứng đủ: ba bản sao cùng dùng một tài khoản quản trị có thể cùng bị xóa; bản sao offline không được thử restore có thể không sử dụng được.

### 7.2. Backup immutability và tách quyền

Một bản sao có **WORM/retention lock** giúp hạn chế khả năng sửa/xóa trong kỳ đã cấu hình, nhưng không bảo đảm dữ liệu trước khi sao lưu là sạch. Cần đánh giá:

1. Backup nằm ở đâu, phiên bản nào, có thuộc policy retention thực sự không?
2. Người quản trị ứng dụng/production có xóa backup hoặc sửa retention được không?
3. Quyền tổ chức, root/admin và KMS có cho phép phá hỏng khả năng khôi phục không?
4. Có alert khi backup job dừng, catalog mất, quyền thay đổi hoặc restore thất bại?
5. Có một hoặc nhiều điểm khôi phục trước cửa sổ có khả năng dữ liệu bị nhiễm độc?
6. Phương án truy cập backup vẫn hoạt động khi IdP, network hoặc primary bị mất?

### 7.3. Tính nhất quán của dữ liệu

Một snapshot có thể là **crash-consistent** hoặc **application-consistent** tùy nền tảng và quá trình tạo. Crash-consistent có thể cần ứng dụng/database replay journal khi phục hồi; application-consistent cố gắng bảo đảm trạng thái ứng dụng phù hợp tại điểm snapshot. Hai cách có mục đích và giới hạn khác nhau; cần chọn theo workload.

Nếu nhiều database, queue và object storage cùng tham gia một giao dịch nghiệp vụ, chỉ restore mỗi hệ thống về điểm gần nhau chưa chắc tạo trạng thái nhất quán. Có thể cần transaction identifier, consistency group, event offset, outbox/inbox, log replay và **kiểm tra bất biến nghiệp vụ**.

Ví dụ, sau phục hồi hệ thống đơn hàng phải kiểm tra: tổng số giao dịch đã ghi sổ, trạng thái thanh toán, các order id không bị tạo trùng và cách giải quyết message đã nhận nhưng chưa commit. Kiểm tra một bảng database có thể đọc được chưa đủ.

### 7.4. Bảo vệ khóa và quyền phục hồi

Backup mã hóa bằng khóa KMS rất hữu ích cho confidentiality, nhưng có thể không khôi phục được nếu:

- Khóa đã bị xóa hoặc hết hiệu lực theo cách không hỗ trợ giải mã bản sao.
- Quyền dùng khóa không tồn tại ở account/region dự phòng.
- Secret cần cho ứng dụng đã hết hạn mà không có cơ chế cấp lại.
- Nhân sự được phép restore chỉ có quyền trên primary và không có quyền tại recovery.
- Quy trình khẩn cấp phụ thuộc hệ thống SSO đang bị sự cố.

**Kiểm thử khôi phục phải bao gồm giải mã và truy cập thực sự**, không chỉ liệt kê bản sao lưu.

## 8. Runbook DR: quy trình con người có thể thực thi

Một **DR runbook** là hướng dẫn thao tác có điều kiện kích hoạt, trình tự, quyết định, điểm kiểm chứng, liên hệ và phương án dừng/rollback. Nó phải đủ cụ thể để người trực thay thế thực hiện trong hoàn cảnh áp lực cao, nhưng vẫn để lại chỗ cho đánh giá rủi ro khi một kịch bản không khớp giả định.

### 8.1. Những phần tối thiểu

| Phần | Nội dung cần có |
|---|---|
| Mục đích và scope | Hệ thống, failure scenario, loại dữ liệu và giới hạn |
| Mục tiêu | RTO, RPO, MBCO, tiêu chí dịch vụ và bảo mật |
| Tiêu chí kích hoạt | Tình huống nào kích hoạt, ai phê duyệt, điều kiện khẩn cấp |
| Vai trò | DR commander, kỹ thuật, security, data owner, nghiệp vụ, communications |
| Điều kiện tiền đề | Quyền truy cập, backup point, artifact, quota, network, dependency |
| Trình tự | Cách cô lập site lỗi, chọn điểm dữ liệu, dựng hạ tầng, khôi phục, chuyển traffic |
| Điểm kiểm soát | Integrity, quyền, malware check, dữ liệu, chức năng, performance, telemetry |
| Quyết định go/no-go | Ai chấp nhận rủi ro khi một điều kiện chưa đạt |
| Rollback/failback | Điều kiện quay về primary, cách xử lý dữ liệu hai chiều |
| Bằng chứng và liên hệ | Log, ticket, artifact, thời gian, đầu mối ngoài hệ thống chính |

### 8.2. Minh họa trạng thái và nhiệm vụ

~~~mermaid
flowchart TD
    INC["Gián đoạn hoặc nghi compromise"] --> TRI["Triage: xác định scope/failure"]
    TRI --> DEC{"Kích hoạt DR?"}
    DEC -- "Không" --> OPS["Incident/operations bình thường"]
    DEC -- "Có" --> SAFE["Cô lập rủi ro, bảo toàn evidence"]
    SAFE --> PICK["Chọn recovery point đáng tin"]
    PICK --> PREP["Chuẩn bị hạ tầng, IAM, KMS, network"]
    PREP --> REST["Restore data và deploy ứng dụng"]
    REST --> TEST{"Security + data + chức năng đạt?"}
    TEST -- "Không" --> FIX["Khắc phục, đổi recovery point hoặc no-go"]
    FIX --> TEST
    TEST -- "Có" --> CUT["Go decision + chuyển traffic"]
    CUT --> MON["Giám sát và đối soát sau phục hồi"]
    MON --> END["Bàn giao, report, cải tiến"]
~~~

Không nên xem sơ đồ là một quy trình tuần tự bắt buộc trong mọi sự cố. Ví dụ, việc bảo toàn chứng cứ có thể phải thực hiện song song với containment; việc kiểm tra dữ liệu có thể bắt đầu trên clean room trước khi tạo đầy đủ môi trường chạy.

### 8.3. Vai trò và quyền ra quyết định

- **Incident/DR commander:** ra quyết định điều phối và chịu trách nhiệm kích hoạt theo chính sách.
- **Service owner:** ưu tiên chức năng, chấp nhận mức degraded mode, xác nhận khả năng phục vụ nghiệp vụ.
- **Platform/Infrastructure:** dựng môi trường, network, routing, compute, storage.
- **Database/Data owner:** chọn recovery point, restore, đối soát và giải quyết sai khác dữ liệu.
- **Security/IR:** xác định trust của backup/artefact, cô lập attacker, kiểm tra credential và control bảo mật.
- **SOC/Monitoring:** giám sát cả primary/recovery, nhận biết hành vi nghi vấn và tình trạng log.
- **Communications/Legal/Privacy:** điều phối thông tin phù hợp khi có nghĩa vụ, đối tượng bị ảnh hưởng.
- **Independent assurance/audit:** kiểm tra điều kiện đạt, bằng chứng và giới hạn của kết luận.

Đối với tổ chức nhỏ, một người có thể đảm nhận nhiều chức năng. Tuy nhiên, các quyết định rủi ro cao như lựa chọn backup nghi nhiễm mã độc hoặc bỏ qua kiểm tra integrity cần có cách phê duyệt và ghi nhận thích hợp.

## 9. Cyber recovery: khôi phục sau sự cố an ninh mạng

Khôi phục sau thảm họa hạ tầng và khôi phục sau tấn công mạng có chung một số kỹ thuật nhưng có **giả định tin cậy khác nhau**. Khi mất điện hoặc hỏng một vùng cloud, bản sao dữ liệu ở vùng khác có thể vẫn đáng tin. Khi bị ransomware hoặc attacker có quyền cao, cả hạ tầng chính, bản sao đồng bộ, kho backup, credential và hệ thống triển khai đều có thể đã bị thao túng.

### 9.1. Rủi ro khôi phục lại một hệ thống đã bị nhiễm

Các trường hợp điển hình:

- Backup được tạo **sau** khi attacker đã cài persistence nhưng trước khi phát hiện.
- Snapshot chứa dữ liệu logic đã bị sửa trái phép và được replicate sang môi trường dự phòng.
- Artifact image hoặc IaC tại registry đã bị thay thế.
- Token/credential cũ còn hiệu lực; attacker có thể đăng nhập ngay vào môi trường vừa phục hồi.
- Backup catalog hoặc retention policy đã bị xóa/chỉnh sửa bởi quyền quản trị bị chiếm.
- Log tại site cũ bị mất, khiến thời điểm xâm nhập đầu tiên không chắc chắn.
- Restore kết nối ngay lại mạng production khi chưa xác minh sự sạch và quyền truy cập.

Vì vậy, **restore thành công về mặt kỹ thuật chưa đồng nghĩa cyber recovery an toàn**.

### 9.2. Quy trình khôi phục tin cậy

1. **Triage và quyết định an toàn:** xác định loại sự cố, nguy cơ còn hoạt động, phạm vi identity và hệ thống đã bị ảnh hưởng; điều phối với đội incident response.
2. **Bảo toàn bằng chứng:** ghi nhận hiện trạng, time window, snapshot/log cần giữ và chain of custody trước các thao tác có thể làm mất dữ liệu.
3. **Cô lập nguồn rủi ro:** tách mạng, vô hiệu credential hoặc chặn đường attacker phù hợp playbook; không để site vừa restore tái kết nối vào môi trường chưa sạch.
4. **Chọn recovery point:** dùng timeline sự cố, audit nguồn độc lập, kiểm tra backup catalog và mức rủi ro để lựa chọn điểm có căn cứ; nếu không thể xác định sạch hoàn toàn thì nêu mức tin cậy và biện pháp giảm thiểu.
5. **Chuẩn bị clean room / môi trường an toàn:** dựng bằng artifact, image, IaC, identity và khóa đã xác minh, giới hạn kết nối, bật logging độc lập.
6. **Restore và kiểm tra:** quét dấu hiệu xâm nhập, xác minh dữ liệu, schema, quyền, khóa, integrity và business invariants.
7. **Thu hồi đường tái xâm nhập:** rotate/revoke credential phù hợp, loại persistence, kiểm tra external access và quyền cấp cao.
8. **Kiểm chứng trước cutover:** security, data và service owner xác nhận tiêu chí phục hồi; rủi ro còn lại được phê duyệt.
9. **Chuyển traffic và giám sát:** theo dõi detection đặc thù, dữ liệu, hiệu năng và hành vi truy cập; sẵn sàng rollback khi có dấu hiệu bất thường.

### 9.3. Kiểm tra bản phục hồi “sạch” có giới hạn gì?

Không thể chứng minh tuyệt đối một môi trường không có bất kỳ mã độc nào. Có thể tăng mức tin cậy bằng cách kết hợp:

- Đối chiếu thời điểm backup với timeline hoạt động đáng ngờ.
- Kiểm tra hash/signature/provenance của artifact.
- Quét với công cụ và rule hiện có, đánh giá khả năng quan sát của công cụ.
- So sánh cấu hình, tài khoản, startup items, scheduled jobs và quyền với baseline.
- Kiểm tra dữ liệu/nghiệp vụ và đối soát giao dịch.
- Xác nhận kiểm soát mạng, IAM, secret và audit log ở môi trường mới.
- Theo dõi sau phục hồi trong thời gian phù hợp với mức rủi ro.

Kết luận phải nêu **phương pháp, nguồn kiểm, phạm vi và rủi ro không thể loại trừ**. Một báo cáo “scan sạch” không đủ nếu chỉ kiểm tra filesystem trong khi credential vẫn còn bị chiếm.

### 9.4. Failover và failback cần thiết kế riêng

**Failover** chuyển hoạt động sang site dự phòng; **failback** chuyển trở lại primary hoặc một môi trường mới sau khi primary được phục hồi. Failback thường khó hơn vì site DR có thể đã nhận ghi mới:

- Cần biết **system of record** tại mỗi thời điểm để tránh hai môi trường cùng nhận ghi độc lập.
- Xác định dữ liệu mới tại recovery và cách đồng bộ an toàn về primary.
- Kiểm tra message offset, idempotency, các hàng đợi và giao dịch treo.
- Xem lại DNS TTL, cache phía khách hàng, session và kết nối đối tác.
- Kiểm tra primary đã được sửa/cách ly nguyên nhân và đạt baseline.
- Có điểm quyết định go/no-go, kế hoạch rollback và phép kiểm sau cutover.

Không nên tự động failback chỉ vì môi trường chính vừa lên lại. Khi có nghi vấn xâm nhập, cần kiểm tra độ tin cậy trước khi chuyển dữ liệu và truy cập.

## 10. Diễn tập và thử nghiệm DR

Khả năng phục hồi là thuộc tính **cần được chứng minh**, không chỉ được suy luận từ thiết kế. Việc thử nghiệm phải có phạm vi, điều kiện an toàn, phương pháp đo, tiêu chí thành công và hồ sơ kết quả.

### 10.1. Các mức diễn tập

| Mức thử nghiệm | Hoạt động | Bằng chứng có được | Giới hạn |
|---|---|---|---|
| **Document / tabletop review** | Đội thảo luận kịch bản, quyết định, liên hệ và trình tự | Runbook review, gaps, vai trò và quyết định | Không chứng minh hệ thống kỹ thuật thực sự restore được |
| **Component restore** | Phục hồi một database, file hoặc VM vào môi trường cô lập | Restore logs, integrity check, duration | Chưa chứng minh dịch vụ đầu cuối đạt RTO |
| **Dependency / integration test** | Khôi phục nhiều thành phần cùng identity/network/config | Kết quả kết nối và đối soát dữ liệu | Phạm vi traffic và lỗi có thể được đơn giản hóa |
| **Controlled failover** | Chuyển một dịch vụ hoặc nhóm workload có kiểm soát | Thời gian, routing, data point, lỗi ứng dụng | Không nhất thiết mô phỏng mất hoàn toàn primary |
| **Full service exercise** | Kiểm tra khôi phục đầu cuối với điều kiện gần thực tế | Actual RTO/RPO, hiệu năng, security và nghiệp vụ | Cần quản lý rủi ro gián đoạn và scope |
| **Cyber recovery exercise** | Dùng giả định backup/artifact/identity bị nghi không tin cậy, restore cô lập | Quy trình clean-room, trust decision, malware/integrity validation | Chỉ xác nhận các kịch bản và dấu hiệu đã kiểm |
| **Failback exercise** | Chuyển dữ liệu và traffic từ DR về primary | Reconciliation, DNS/session tests, quyết định rollback | Cần chuẩn bị xử lý split brain và dữ liệu phát sinh mới |

Nên phối hợp các mức thử thay vì chỉ chạy một tabletop rồi đánh dấu **“DR test PASS”** cho toàn hệ thống.

### 10.2. Thiết kế một test case có kiểm soát

Mỗi test case phải có:

1. **Scenario:** ví dụ mất hoàn toàn region chính, mất KMS hay corruption logic.
2. **Scope:** dịch vụ, database, message stream, identity, các vùng và người tham gia.
3. **Prerequisites:** bản backup, access, capacity, quyền, thời gian, điều kiện stop.
4. **Baseline:** cấu hình và trạng thái trước test, target RTO/RPO và data point kỳ vọng.
5. **Trigger:** mốc bắt đầu T0 rõ ràng, ai cho phép phát lệnh.
6. **Steps:** runbook version, thao tác được phép, cách ghi timestamp.
7. **Assertions:** data integrity, functional tests, performance, security, routing, monitoring, nghiệp vụ.
8. **Evidence:** logs, kết quả script, màn hình khi cần, ID tài nguyên, các mốc, người đánh giá.
9. **Rollback:** phương án trở về trạng thái ổn định, dừng thử khi vượt ngưỡng an toàn.
10. **Post-test:** findings, owner, deadline và kế hoạch retest.

**Không chủ động phá hủy production chỉ để thử DR.** Những phép thử có nguy cơ cao nên triển khai trong môi trường cô lập hoặc theo quy trình diễn tập đã phê duyệt, với cơ chế giới hạn tác động và rollback.

### 10.3. Positive test và negative test

Đừng chỉ kiểm tra rằng khôi phục từ một backup tốt thành công. Phải thử các trường hợp khi điều kiện không đáp ứng:

- **Positive:** chọn backup hợp lệ, dựng đủ hạ tầng, service pass health và data reconciliation.
- **Negative — không có key:** backup còn nhưng quyền giải mã bị thiếu; runbook phải phát hiện, không báo PASS giả.
- **Negative — backup corrupt:** checksum hoặc application validation thất bại; chuyển sang recovery point khác theo quy trình.
- **Negative — không đủ quota:** site DR không khởi tạo đủ capacity; alert và escalation đúng.
- **Negative — lệch cấu hình:** policy thiếu, credential quá quyền hoặc logging chưa bật; chặn go-live nếu vi phạm tiêu chí bắt buộc.
- **Negative — replay:** sau restore message broker phát lại message; ứng dụng có xử lý idempotent hoặc reconciliation đúng.
- **Negative — primary vẫn đang ghi:** phải phát hiện nguy cơ split brain và chặn luồng ghi xung đột.

Một bài thử âm thành công khi hệ thống **nhận biết và xử lý điều kiện lỗi theo thiết kế**, không nhất thiết là mọi bước phục hồi vẫn hoàn tất.

### 10.4. Tính đại diện của diễn tập

Diễn tập restore trên database 2 GB không chứng minh thời gian khôi phục khi production có 15 TB. Test một site cloud cùng account không chứng minh chịu được mất hoàn toàn account. Test khi mọi nhân sự đều có mặt không chứng minh runbook sử dụng được khi người vận hành chính vắng mặt.

Cần ghi **dữ liệu, khối lượng, cấu hình, vùng, phiên bản và loại sự cố đã được giả lập**. Khi không thể mô phỏng production đầy đủ, kết luận phải nêu giả định suy rộng và kế hoạch kiểm chứng bổ sung.

## 11. Đo RTO/RPO sau một diễn tập

### 11.1. Dữ kiện giả định

Một dịch vụ đơn hàng có yêu cầu:

- **RTO = 120 phút** kể từ lúc gián đoạn.
- **RPO = 15 phút** tại điểm dữ liệu nhất quán có thể phục hồi.
- **MBCO:** tiếp nhận và xác nhận đơn hàng cơ bản, không bắt buộc có dashboard phân tích.
- **Security gate:** quyền truy cập tối thiểu, log/audit và các kiểm soát thiết yếu phải hoạt động trước khi chuyển traffic chính thức.

Đội diễn tập giả lập mất site chính tại **09:00 UTC**.

| Thời điểm | Hoạt động | Bằng chứng |
|---|---|---|
| 08:52 | Điểm dữ liệu nhất quán mới nhất còn phục hồi được | Backup/transaction-log catalog E-01 |
| 09:00 | Site chính được đánh dấu không khả dụng (T0) | Test controller/event E-02 |
| 09:08 | DR commander quyết định kích hoạt quy trình | Approval E-03 |
| 09:21 | Recovery environment sẵn sàng hạ tầng và quyền | IaC/IAM verification E-04 |
| 09:49 | Database phục hồi xong và qua kiểm tra kỹ thuật | Restore result E-05 |
| 10:12 | Ứng dụng đạt health check sơ bộ | Application test E-06 |
| 10:31 | Đối soát dữ liệu và queue đạt các bất biến đã định | Reconciliation E-07 |
| 10:39 | Kết quả IAM, audit logging, certificate và detection test đạt | Security check E-08 |
| 10:44 | Chuyển traffic, kiểm tra giao dịch đầu cuối và xác nhận MBCO đạt (T1) | Synthetic transaction E-09 |

Các ID và timestamp đều **giả định**, nhằm minh họa phương pháp đo.

### 11.2. Tính kết quả

**Achieved recovery duration = 10:44 − 09:00 = 104 phút.**

**Achieved recovery point lag = 09:00 − 08:52 = 8 phút.**

Nếu tất cả điều kiện trong scope đã được xác minh và dữ liệu tại 08:52 thực sự nhất quán, kết quả thỏa RTO 120 phút và RPO 15 phút **đối với kịch bản và dịch vụ đã diễn tập**.

Không nên dùng **10:12** làm T1 vì tại mốc này mới có health check, dữ liệu/queue và security gate chưa được xác minh. Cũng không nên dùng 09:08 làm thời điểm bắt đầu đo nếu BIA quy định mốc từ lúc gián đoạn 09:00.

### 11.3. Phân loại kết luận có giới hạn

Kết luận phù hợp:

> Trong diễn tập mất site chính theo kịch bản DR-EX-001, dịch vụ đơn hàng đã đạt MBCO sau 104 phút, với điểm dữ liệu nhất quán cách mốc gián đoạn 8 phút. Các phép kiểm functional, reconciliation, identity và logging tại recovery đều PASS trong scope đã ghi nhận. Kết quả chưa chứng minh hệ thống đáp ứng khi xảy ra ransomware hoặc đồng thời mất KMS tại cả hai vùng.

Kết luận không phù hợp:

> DR hoàn toàn an toàn và chắc chắn luôn phục hồi trong 104 phút trước mọi thảm họa.

### 11.4. Những điều một phép thử không thể hiện hết

Một bài test tốt có thể vẫn chưa bao phủ:

- Mất năng lực của vendor hoặc nhà cung cấp định danh dùng chung.
- Khôi phục vào thời điểm dữ liệu có corruption lâu ngày.
- Failback sau nhiều ngày phát sinh dữ liệu tại site dự phòng.
- Khối lượng production thực tế vào giờ cao điểm.
- Sự vắng mặt của nhân sự chủ chốt, khẩn cấp liên lạc ngoài giờ.
- Dữ liệu nhạy cảm có yêu cầu kiểm soát pháp lý riêng.
- Tấn công vào backup catalog, khóa hoặc môi trường dự phòng.

Chúng nên được ghi vào **test coverage và risk register**, không tự suy ra PASS từ bài diễn tập chính.

## 12. Bộ baseline control cho disaster recovery assurance

Một baseline hiệu quả cần viết thành các **assertion có thể kiểm tra**. Bảng sau là khung nội dung phục vụ học tập, cần chỉnh theo hệ thống, rủi ro và yêu cầu nội bộ.

| ID | Control | Điều kiện đạt mong muốn | Bằng chứng và phép kiểm |
|---|---|---|---|
| **DR-01** | Business impact / criticality | Dịch vụ có owner, mức quan trọng, RTO/RPO/MBCO được phê duyệt | BIA record, phê duyệt business owner, service catalog |
| **DR-02** | Dependency inventory | Các tài sản, dữ liệu, IAM, network, key và đối tác cần khôi phục được kiểm kê | Service dependency map đối soát với thực tế |
| **DR-03** | Threat/failure scenario | Có scenario phù hợp các failure domain quan trọng | Threat model, risk assessment và test coverage register |
| **DR-04** | DR strategy | Chiến lược thiết kế đáp ứng mục tiêu và mô hình lỗi đã định | Kiến trúc, capacity plan, quyết định rủi ro |
| **DR-05** | Backup coverage | Nguồn dữ liệu/cấu hình bắt buộc có backup đúng kỳ và kiểm tra tình trạng | Backup inventory, job reports, đối soát nguồn |
| **DR-06** | Backup protection | Backup được phân quyền, mã hóa và bảo vệ sửa/xóa theo chính sách | Retention, IAM/KMS policy, test deny và audit |
| **DR-07** | Restore readiness | Có backup/catalog/key và khả năng restore thật | Restore test vào môi trường cô lập, log giải mã |
| **DR-08** | Data consistency | Điểm phục hồi có thể sử dụng và đáp ứng bất biến nghiệp vụ | DB integrity, transaction/queue reconciliation |
| **DR-09** | Infrastructure readiness | Region/site dự phòng có quota, hạ tầng, route và artifact phù hợp | IaC deploy test, capacity check, routing check |
| **DR-10** | Identity/security continuity | IAM, KMS, secret, logging và control quan trọng hoạt động sau phục hồi | Break-glass drill, authz test, security test |
| **DR-11** | Runbook governance | Kế hoạch có owner, activation criteria, version và phê duyệt | Runbook, approval history, contact exercise |
| **DR-12** | End-to-end recovery | Dịch vụ đáp ứng RTO và MBCO trong scenario được kiểm | Mốc T0/T1, app/data/business acceptance |
| **DR-13** | Recovery point | Mức mất dữ liệu đạt RPO bằng phép đo trên điểm dữ liệu nhất quán | Catalog và mốc transaction, restore verification |
| **DR-14** | Cyber recovery | Có phương pháp tìm điểm restore tin cậy, tránh tái nhiễm và khôi phục quyền | Clean room test, artifact trust và credential revoke |
| **DR-15** | Failback | Có phương án trở lại môi trường chính và kiểm tra đối soát | Controlled failback drill, reconciliation, rollback |
| **DR-16** | Continuous improvement | Finding, ngoại lệ và kết quả retest được quản lý theo owner/hạn | Action register, exception, regression/drill results |
| **DR-17** | Communications and decision | Quyết định kích hoạt, chuyển traffic, phục hồi và thông tin có chủ thể chịu trách nhiệm | Incident/DR case, approval và communications log |
| **DR-18** | Evidence handling | Kết quả kiểm tra có nguồn, phạm vi, thời gian và tính toàn vẹn phù hợp | Evidence manifest, audit access, verification record |

### 12.1. Xác minh thiết kế và xác minh hiệu lực

Một số tài liệu được xem là **bằng chứng thiết kế**, ví dụ sơ đồ mạng, quyết định RTO và chính sách backup. Tuy nhiên, để chứng minh **control hoạt động**, cần thêm kiểm tra:

- **DR-05:** chính sách backup đã gắn đủ nguồn và job thực sự ghi dữ liệu.
- **DR-07:** restore vào môi trường thử thành công, ứng dụng đọc được dữ liệu.
- **DR-10:** người được phân công có thể đăng nhập và dùng KMS; người không được phép bị từ chối; audit hoạt động.
- **DR-12:** đồng hồ đo đúng mốc T0/T1, kết quả functional và performance đáp ứng MBCO.
- **DR-13:** có xác nhận last consistent data point thay vì chỉ nhìn thời gian file snapshot.
- **DR-14:** bản phục hồi có được đánh giá theo threat scenario về persistence và credential bị chiếm.
- **DR-16:** sau khi sửa một finding, test lại trên cấu hình thực tế.

Những dòng “đã có runbook”, “backup daily enabled” hoặc “DR region configured” mới cho biết một phần trạng thái, không tự chứng minh đã đạt mục tiêu phục hồi.

### 12.2. Phân loại trạng thái kết quả

Nên định nghĩa nhất quán:

- **PASS:** đủ bằng chứng kiểm thử rằng assertion đã đạt trong phạm vi.
- **FAIL:** có bằng chứng assertion không đạt.
- **INCONCLUSIVE:** thiếu bằng chứng hoặc thử nghiệm không đánh giá đúng điều kiện.
- **NOT_TESTED:** assertion chưa được thử hiệu lực.
- **NOT_APPLICABLE:** không áp dụng và có lý do/phê duyệt rõ.
- **ACCEPTED_RISK:** chưa đạt nhưng đã có quyết định chấp nhận rủi ro có điều kiện; không chuyển thành PASS.

Khi cần, có thể dùng trạng thái **PASS_WITH_SCOPE** để nhấn mạnh mức bao phủ hẹp; phải giải thích đây là quy ước báo cáo nội bộ.

## 13. Thu thập bằng chứng và lập báo cáo diễn tập

### 13.1. Evidence register

Bằng chứng nên có:

- **Assessment/test ID**, scenario, service, environment, version của runbook.
- **Nguồn và mốc thời gian:** hệ thống nào tạo log, timestamp theo UTC, timezone và clock accuracy.
- **Tài sản và phiên bản:** database snapshot/backup ID, image digest, IaC revision, cloud region/account.
- **Dữ liệu kiểm tra:** restore logs, schema/integrity output, số liệu đối soát, synthetic transactions.
- **Quyền và giám sát:** IAM/KMS/authz tests, log/alert tại site dự phòng, change record.
- **Kết quả và giới hạn:** assertion, expected, observed, verdict, owner và những gì chưa thử.
- **Bảo quản:** vị trí lưu, quyền truy cập, integrity/checksum khi cần, chính sách retention và lịch sử thay đổi.

Không lưu token, private key, dữ liệu khách hàng thật hoặc ảnh chứa secrets vào báo cáo chỉ để có thêm bằng chứng. Có thể giữ raw evidence ở kho bảo vệ và đưa reference phù hợp vào báo cáo kiểm toán.

### 13.2. Mẫu hồ sơ DR exercise

Đây là **YAML minh họa cấu trúc báo cáo**, không phải cấu hình chạy trực tiếp của sản phẩm DR nào:

~~~yaml
exercise_id: "DR-EX-2026-001"
report_version: "v1"
service: "orders-api"
environment: "staging-recovery"
scenario: "primary-site-unavailable"
tested_at: "2026-11-28T09:00:00Z"
runbook_version: "dr-orders-v4"
business_approval:
  rto_minutes: 120
  rpo_minutes: 15
  minimum_service: "accept-and-confirm-orders"
timeline:
  disruption_at: "2026-11-28T09:00:00Z"
  dr_activated_at: "2026-11-28T09:08:00Z"
  recovery_verified_at: "2026-11-28T10:44:00Z"
data:
  last_consistent_recovery_point_at: "2026-11-28T08:52:00Z"
  restore_point_reference: "backup-catalog/example-point-852"
observed:
  recovery_duration_minutes: 104
  recovery_point_lag_minutes: 8
  business_functional_test: "PASS"
  data_reconciliation: "PASS"
  identity_and_logging: "PASS"
result: "PASS_WITH_SCOPE"
evidence:
  - "evidence/dr-ex001/backup-catalog.json"
  - "evidence/dr-ex001/restore-result.json"
  - "evidence/dr-ex001/transactions-test.json"
  - "evidence/dr-ex001/security-validation.json"
limitations:
  - "Không đánh giá ransomware hoặc mất shared KMS"
  - "Diễn tập trong staging có tải thấp hơn production"
assessor: "security-assurance-team"
retest_required_for_open_findings: true
~~~

Một báo cáo thực tế cần có **bằng chứng về T0, T1, điểm nhất quán và các phép kiểm** tương ứng, không chỉ các số đã điền. Tính toán phải được tái kiểm trên log/counter và dữ liệu có nguồn rõ.

### 13.3. Kiểm tra tính trung thực của kết luận

Trước khi chấp nhận kết quả PASS:

1. T0 là mốc gián đoạn theo BIA, không bị dời sang lúc bắt đầu thao tác.
2. T1 là mốc hoàn tất tiêu chí **dịch vụ nghiệp vụ và bảo mật** đã định, không phải lúc server khởi động.
3. Điểm phục hồi Tdata là **last verified consistent point**; không lấy thời gian backup job kết thúc làm thời gian dữ liệu mới nhất nếu semantics khác.
4. Phạm vi nguồn dữ liệu và thành phần phụ thuộc đã được đối chiếu.
5. Test data, tải, region, quyền và kịch bản có đại diện cho failure model đang đánh giá.
6. Có ghi rõ điều kiện **NOT_TESTED** hoặc hạn chế suy rộng kết quả.
7. Evidence đủ để bên khác truy lại tính toán và chứng minh đã sửa finding.

Một hệ thống đạt RTO nhưng không đạt RPO chỉ được coi là đáp ứng **một phần mục tiêu**, không tự đánh dấu DR toàn diện PASS.

## 14. Case study: mất primary và phát hiện dữ liệu chưa nhất quán

Một doanh nghiệp có hệ thống đơn hàng sử dụng database và message broker. BIA yêu cầu **RTO 2 giờ**, **RPO 15 phút**, còn MBCO là khả năng nhận đơn an toàn và không tạo trùng giao dịch. Môi trường DR dùng warm standby và backup dữ liệu theo kỳ.

### 14.1. Diễn biến

Tại 09:00 UTC, vùng chính không thể truy cập. Đội vận hành kích hoạt DR, khôi phục database từ điểm 08:50 và triển khai API tại vùng dự phòng. Đến 09:48, API health check PASS. Đội nghiệp vụ thử gửi đơn và phát hiện **một số sự kiện thanh toán có thể bị xử lý hai lần** do message broker đang chứa offset không khớp trạng thái database.

Nếu chỉ dựa trên API healthy lúc 09:48, hệ thống có vẻ đạt RTO dưới một giờ. Nhưng dịch vụ chưa đáp ứng MBCO về tính an toàn giao dịch.

### 14.2. Điều tra và khôi phục

Đội recovery thực hiện:

1. **Tạm dừng mở traffic công khai** để tránh nhân đôi giao dịch.
2. Đối chiếu transaction ID, order ID, trạng thái thanh toán và broker offset tại mốc phục hồi.
3. Xác định những message đã phát nhưng chưa commit, những message đã xử lý nhưng còn trong queue.
4. Áp dụng cơ chế idempotency/deduplication theo đặc tính ứng dụng; kiểm tra tính đúng của trạng thái dữ liệu, không mặc định xóa queue.
5. Chạy nghiệp vụ mẫu với các kịch bản retry và message replay.
6. Xác minh các control truy cập, logging, route, secret và KMS.
7. Chỉ chuyển traffic sau khi các test và người có thẩm quyền xác nhận.

Giả sử hoàn tất kiểm chứng và chuyển traffic ở **10:40 UTC**, actual recovery duration là **100 phút** tính từ 09:00, nằm trong RTO 120 phút. Tuy nhiên, điểm dữ liệu mới nhất là **08:50**, tức recovery point lag **10 phút**. RPO 15 phút chỉ đạt nếu đã chứng minh điểm 08:50 nhất quán và không có dữ liệu thuộc phạm vi cần giữ bị bỏ ngoài backup.

### 14.3. Kết luận assurance

| Kiểm soát | Kết quả ví dụ | Cơ sở |
|---|---|---|
| Khôi phục hạ tầng và ứng dụng | PASS_WITH_SCOPE | Ứng dụng hoạt động trong thời gian mục tiêu sau khi sửa |
| RTO đầu cuối | PASS_WITH_SCOPE | 100 phút từ disruption đến MBCO đạt |
| RPO dữ liệu | PASS_WITH_SCOPE nếu điểm 08:50 đã xác minh | Recovery point lag 10 phút; phải đối soát phạm vi |
| Dữ liệu/message ban đầu | FAIL tại checkpoint 09:48 | Phát hiện nguy cơ xử lý trùng |
| Phép kiểm phát hiện lỗi dữ liệu | PASS | Integration test phát hiện sai khác trước khi mở traffic |
| Cyber recovery | NOT_TESTED | Kịch bản này chưa giả lập attacker hoặc backup bị nhiễm |

**Bài học:** phát hiện lỗi trong diễn tập là kết quả tích cực của quá trình assurance, nhưng finding về thiết kế khôi phục broker vẫn cần xử lý. Không được biến việc “đã sửa thủ công lần này” thành chứng minh rằng lần sau sẽ tự khôi phục đúng.

### 14.4. Corrective actions

- Thêm kiểm tra transaction/outbox và broker offset vào runbook.
- Đưa deduplication/idempotency test vào CI và diễn tập DR.
- Ghi checkpoint dữ liệu nghiệp vụ liên kết database và message processing.
- Đo thời gian cho toàn bộ kiểm tra dữ liệu trong RTO, không chỉ thời gian khởi tạo hạ tầng.
- Diễn tập lại khi đổi broker, schema, consumer logic hoặc hạ tầng replication.
- Kiểm tra failback để dữ liệu phát sinh tại DR không tạo xung đột khi quay về primary.

## 15. Quản trị rủi ro, ngoại lệ và cải tiến liên tục

### 15.1. Khi kết quả diễn tập chưa đạt

Một finding DR nên có các trường:

| Trường | Nội dung |
|---|---|
| Finding ID | Định danh kết nối test, risk và action |
| Control ID | Assertion nào không đạt |
| Scope | Service, environment, dependency và failure scenario |
| Expected/observed | Điều kiện mục tiêu và số liệu thực đo |
| Evidence | Test run, log, backup point, timestamps, kết quả kiểm |
| Impact/risk | Hậu quả nghiệp vụ, security và likelihood |
| Owner/severity/due date | Người xử lý, ưu tiên và hạn phù hợp |
| Remediation | Thay đổi kỹ thuật hoặc quy trình |
| Compensating control | Biện pháp tạm thời khi chưa khắc phục ngay |
| Retest | Cách kiểm lại, người phê duyệt, kết quả sau sửa |

Ví dụ, nếu một ứng dụng mục tiêu RTO 60 phút nhưng diễn tập thực tế mất 180 phút do không đủ quota, biện pháp sửa không chỉ là “tăng tốc restore”. Phải xác định điểm nghẽn capacity, quyền cấp phát và phương pháp dự trữ quota; sau đó **thử lại**.

### 15.2. Ngoại lệ phải có hạn và giới hạn

Một số ứng dụng chưa thể đáp ứng RTO/RPO ngay vì chi phí, đặc tính dữ liệu hoặc khả năng của nhà cung cấp. Ngoại lệ nên nêu:

- Mục tiêu nào không đạt và trạng thái bằng chứng hiện có.
- Ảnh hưởng đến nghiệp vụ, nghĩa vụ hợp đồng/pháp lý nếu áp dụng.
- Biện pháp bù trừ: vận hành thủ công, giảm quyền, backup thêm, giám sát hoặc capacity reserve.
- Người chấp thuận rủi ro, owner, thời hạn và kế hoạch nâng cấp.
- Điều kiện cần đánh giá lại khi dữ liệu, traffic, kiến trúc hoặc nghĩa vụ thay đổi.

Ngoại lệ được phê duyệt **không biến FAIL thành PASS**; báo cáo nên phân biệt mức rủi ro được chấp nhận với khả năng phục hồi đã được chứng minh.

### 15.3. Đưa kiểm tra DR vào vòng đời thay đổi

~~~mermaid
flowchart LR
    BIA["BIA + risk objectives"] --> DESIGN["DR architecture + controls"]
    DESIGN --> BUILD["Provision + backup + runbook"]
    BUILD --> TEST["Restore / failover / security test"]
    TEST --> DEC{"Assertions đạt?"}
    DEC -- "Có" --> MON["Theo dõi drift và định kỳ diễn tập"]
    DEC -- "Không" --> FIND["Finding + owner + due date"]
    FIND --> FIX["Khắc phục + retest"]
    FIX --> TEST
    MON --> CHANGE["Thay đổi ứng dụng, dữ liệu hoặc phụ thuộc"]
    CHANGE --> BIA
~~~

Các trigger cần kiểm tra lại gồm:

- Thêm database, stream, object store hoặc nhà cung cấp phụ thuộc.
- Đổi RTO/RPO trong BIA, tăng quy mô dữ liệu hoặc thay đổi traffic peak.
- Thay IAM, KMS, certificate, DNS, network policy hoặc account boundary.
- Cập nhật phiên bản runtime/DB, thay công cụ backup, chuyển sang IaC mới.
- Tạo thêm region/cluster hoặc đổi chính sách dữ liệu/retention.
- Phát hiện lỗ hổng ảnh hưởng artifact và khả năng restore.
- Sau incident hoặc diễn tập có finding chưa đạt.

### 15.4. KPI có ý nghĩa

| KPI | Phương pháp đo | Giới hạn |
|---|---|---|
| **DR coverage** | Số dịch vụ trọng yếu có chiến lược và runbook được phê duyệt / tổng dịch vụ trọng yếu | Có tài liệu chưa chứng minh đã kiểm thử |
| **Verified recovery coverage** | Dịch vụ đã diễn tập đạt RTO/RPO và security gate / tổng dịch vụ cần diễn tập | Cần ghi scope/failure scenarios, không chỉ số service |
| **Restore success rate** | Restore test đạt toàn bộ assertion / tổng restore test hợp lệ | Không chỉ kiểm tra job chạy thành công |
| **Achieved RTO/RPO** | Thời gian và độ lùi dữ liệu đo theo T0/T1/Tdata | So sánh theo cùng failure model và quy mô |
| **Backup freshness** | Độ trễ điểm backup mới nhất so với kỳ vọng | Backup mới không đồng nghĩa sạch/nhất quán |
| **Recovery data integrity** | Điểm restore đạt kiểm tra integrity/nghiệp vụ / điểm restore được kiểm | Kiểm tra quá ít tình huống có thể bỏ sót |
| **Runbook freshness** | Runbook được review sau thay đổi quan trọng / tổng runbook cần review | Review trên giấy chưa chứng minh thực thi |
| **Open critical findings** | Finding DR nghiêm trọng còn mở theo thời gian | Phải có số liệu retest và owner |
| **Failback readiness** | Kịch bản failback đã thử và đối soát thành công / kỳ vọng | Nhiều chương trình DR chỉ thử failover |
| **Security control parity** | Control bắt buộc đạt ở recovery / tổng control bắt buộc tại recovery | Không gộp ngoại lệ chưa kiểm thành đạt |

Nếu một dashboard báo **100% backup jobs successful** nhưng không có thử restore, đội assurance chỉ có cơ sở nói về mức độ hoàn thành công việc sao lưu, **chưa có bằng chứng hệ thống phục hồi được**.

## 16. Những hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “Có backup nên có DR.” | DR cần hạ tầng, runbook, danh tính, network, restore, kiểm tra dữ liệu, nghiệp vụ và thời gian. |
| “HA đã bật nên không cần DR.” | HA chỉ bao phủ một số failure domains; corruption, account lockout hoặc mất cả region vẫn cần phương án. |
| “Hai region nghĩa là an toàn trước mọi lỗi.” | Có thể chung account, IAM, KMS, CI/CD, DNS và lỗi logic nhân bản. |
| “RTO là thời gian boot được server.” | RTO dịch vụ chỉ đạt khi toàn bộ điều kiện phục hồi trong scope được đáp ứng. |
| “RPO 0 nghĩa là không thể mất dữ liệu.” | Cần kiểm chứng semantics commit và failure model; lỗi logic vẫn có thể được replicate. |
| “Backup job success tức dữ liệu restore được.” | Phải thử giải mã, dựng ứng dụng, integrity và business invariants. |
| “Snapshot mới nhất luôn tốt nhất.” | Snapshot có thể chứa corruption hoặc malware; cần chọn điểm đáng tin. |
| “Failover là kết thúc DR.” | Cần kiểm chứng service, security, dữ liệu, monitoring và có thể cần failback. |
| “Mọi DR test đều chứng minh được production.” | Scope, tải, dữ liệu, quyền và loại lỗi của test quyết định mức độ suy rộng. |
| “DR site mới có thể tắt logging tạm cho nhanh.” | Các security gate phải được đánh giá; bỏ control có thể tạo rủi ro mới. |
| “RTO bắt đầu khi đội bấm runbook.” | Phải theo mốc T0 trong BIA, thường liên quan thời điểm gián đoạn. |
| “Đã đóng ticket nên DR PASS.” | Cần retest thực tế trên phạm vi của finding và bảo vệ evidence. |
| “Ransomware chỉ cần restore backup.” | Cần đánh giá sạch dữ liệu, identity, artifact, persistence và nguy cơ tái xâm nhập. |
| “Chuyển về primary lúc nào cũng an toàn.” | Phải xử lý dữ liệu đã ghi tại DR, tránh split brain và xác minh primary sạch. |

## 17. Bài tập tự kiểm tra

**Câu 1.** Một hệ thống database có replication sang region B. Nếu tại region A người dùng xóa nhầm bảng và thay đổi được replicate sang B, replication đã đáp ứng khôi phục dữ liệu chưa?

**Gợi ý:** Chưa chắc. Replica có thể chứa cùng lỗi logic. Cần backup hoặc point-in-time recovery đến trạng thái trước lỗi, cùng kiểm tra tính nhất quán và nghiệp vụ.

**Câu 2.** BIA quy định RTO 90 phút. Diễn tập bắt đầu gián đoạn lúc 10:00, đội quyết định kích hoạt DR lúc 10:20, hệ thống đáp ứng MBCO lúc 11:25. RTO thực tế đo từ đâu và kết quả là bao nhiêu?

**Gợi ý:** Theo mốc gián đoạn 10:00 đã định trong BIA; đạt MBCO lúc 11:25, thời gian thực tế là 85 phút, đạt RTO 90 phút nếu mọi điều kiện bắt buộc khác cũng đạt.

**Câu 3.** RPO mục tiêu 10 phút, site chính hỏng lúc 09:00. Backup mới nhất có thể restore nhất quán đến 08:43. Có đạt RPO không?

**Gợi ý:** Không. Độ lùi dữ liệu là 17 phút, vượt mục tiêu 10 phút. Phải điều tra lý do và xác định biện pháp sửa.

**Câu 4.** Một môi trường dự phòng dựng từ IaC trong 20 phút nhưng không dùng được KMS để giải mã dữ liệu. Có thể báo RTO 20 phút không?

**Gợi ý:** Không. Phục hồi chưa đạt tiêu chí dịch vụ và dữ liệu. Cần khắc phục quyền/khóa và đo đến lúc có bằng chứng khôi phục hoàn chỉnh.

**Câu 5.** Vì sao việc restore thành công sau ransomware không tự chứng minh an toàn?

**Gợi ý:** Backup có thể chứa persistence, dữ liệu bị sửa hoặc artifact độc hại; credential cũ và đường mạng vẫn bị chiếm. Cần clean recovery, kiểm tra nguồn tin cậy, quyền, dữ liệu và giám sát.

**Câu 6.** Một ứng dụng chạy active-active hai vùng. Có phải RTO và RPO bằng 0 trong mọi trường hợp không?

**Gợi ý:** Không. Thiết kế có thể giảm gián đoạn nhưng còn consistency, network partition, split brain, lỗi chung và giới hạn replication/commit. Cần kiểm thử theo failure model.

**Câu 7.** Một diễn tập DR PASS về RTO/RPO nhưng logging ở recovery không hoạt động. Kết luận chung nên là gì?

**Gợi ý:** RTO/RPO có thể PASS trong scope đã đo, nhưng security control bắt buộc FAIL; DR assurance tổng thể không đạt nếu logging là điều kiện cần trước cutover.

**Câu 8.** Tại sao cần diễn tập failback riêng với failover?

**Gợi ý:** Trong thời gian chạy ở DR, dữ liệu và message tiếp tục thay đổi; chuyển về primary cần đồng bộ, tránh ghi xung đột, kiểm tra route và rollback. Failover PASS không tự chứng minh failback PASS.

## 18. Bài tập tình huống: lập DR assurance plan

Bạn được giao đánh giá khả năng phục hồi một nền tảng API xử lý đơn hàng. Nền tảng có hai cluster Kubernetes ở hai region, database chính với replication bất đồng bộ, message broker, object storage, KMS, IdP và DNS. Đội vận hành nói rằng “có nhiều replica và backup nên DR đã hoàn thành”.

**Thông tin giả định:**

- BIA yêu cầu RTO 2 giờ và RPO 15 phút cho giao dịch đặt hàng.
- Backup database mỗi giờ; transaction log được sao lưu theo chu kỳ ngắn hơn.
- DR cluster được triển khai nhưng chưa thử cho tải tương đương production.
- KMS key và một phần secret có quyền truy cập chỉ ở primary account.
- Ứng dụng phụ thuộc broker và object metadata; runbook hiện chỉ mô tả restore database.
- SOC chưa cấu hình alert tại region DR.
- Có nguy cơ tài khoản quản trị primary và DR sử dụng cùng một danh tính đặc quyền.

**Yêu cầu thực hành:**

1. Vẽ dependency map và xác định ít nhất bốn failure domains có thể dẫn đến gián đoạn.
2. Liệt kê dữ liệu và cấu hình cần phục hồi; chỉ ra các thành phần bị bỏ sót trong runbook.
3. So sánh chiến lược hiện có với yêu cầu RTO/RPO; nêu bằng chứng còn thiếu.
4. Thiết kế một diễn tập controlled failover an toàn, gồm T0, T1, Tdata và điều kiện stop/rollback.
5. Định nghĩa các bài kiểm tra dữ liệu: restore, transaction consistency, broker offset, object metadata và quyền.
6. Xây dựng security gate trước cutover: IAM, KMS, secrets, logging/monitoring, artifact trust và quyền truy cập khẩn cấp.
7. Lập báo cáo PASS/FAIL/INCONCLUSIVE cho ít nhất sáu control DR-01..DR-18, với evidence IDs giả định.
8. Đề xuất corrective actions có owner, deadline, retest và kế hoạch diễn tập failback.

**Tiêu chí đạt:** kết quả phân biệt được năng lực được thiết kế với năng lực đã chứng minh; chỉ kết luận RTO/RPO khi phép đo bao phủ cả dịch vụ nghiệp vụ, dữ liệu và các điều kiện kiểm tra an toàn.

## 19. Checklist DR assurance trước khi chấp nhận một hệ thống

- [ ] Mỗi dịch vụ trọng yếu có owner, BIA, RTO/RPO/MBCO và phạm vi đã phê duyệt.
- [ ] Có inventory tài sản, dependency và failure domain; nhận diện những phụ thuộc chung.
- [ ] Kiến trúc DR được chọn theo kịch bản rủi ro và mục tiêu cụ thể.
- [ ] Backup/replication bao phủ đủ dữ liệu, schema, transaction log, metadata và cấu hình.
- [ ] Backup được bảo vệ bằng IAM, encryption, retention và biện pháp chống sửa/xóa phù hợp.
- [ ] Restore đã được thử trên dữ liệu đủ đại diện và có kiểm tra tính nhất quán.
- [ ] KMS, secrets, identity, break-glass access và artifact trust được thử tại nơi khôi phục.
- [ ] Có khả năng cấp đủ compute, network, DNS, certificate, quota và kết nối đối tác.
- [ ] Runbook có version, activation criteria, vai trò, quyết định và kế hoạch rollback.
- [ ] Đã diễn tập end-to-end với timestamp T0/T1/Tdata và chứng minh RTO/RPO theo BIA.
- [ ] Đã kiểm tra ứng dụng, nghiệp vụ, transaction/message consistency và performance tối thiểu.
- [ ] Monitoring, logging, audit, alert và security controls hoạt động tại môi trường recovery.
- [ ] Có cyber recovery plan khi bản sao và danh tính có thể bị xâm phạm.
- [ ] Có cách tránh split brain và kiểm tra failback sau khi dữ liệu phát sinh ở DR.
- [ ] Báo cáo diễn tập nêu nguồn bằng chứng, scope, hạn chế, trạng thái và người phê duyệt.
- [ ] Findings/ngoại lệ có owner, due date, kiểm thử lại và rủi ro còn lại.
- [ ] Thay đổi hệ thống, dữ liệu, hạ tầng, cloud account và rủi ro kích hoạt việc rà soát DR.
- [ ] Đội có thể thực hiện runbook và giao tiếp khi hạ tầng chính hoặc người trực chính không sẵn có.

## Kết luận

**Disaster recovery là khả năng khôi phục hệ thống, dữ liệu và dịch vụ sau một gián đoạn nghiêm trọng trong giới hạn đã được nghiệp vụ chấp thuận.** Nó bao gồm backup, replication, hạ tầng dự phòng, quyền, khóa, mạng, con người, runbook, quyết định chuyển traffic và kiểm chứng tính đúng đắn của trạng thái sau phục hồi.

Đối với **SECURITY_SECURITY_ASSURANCE**, một kế hoạch DR chỉ trở thành năng lực có thể tin cậy khi tổ chức **xác định rõ failure scenario và mục tiêu RTO/RPO, thử khôi phục thực tế, đo bằng mốc thời gian đúng, xác minh dữ liệu và an toàn bảo mật, lưu bằng chứng, xử lý finding rồi retest**. Nhờ chu trình đó, khả năng phục hồi được đánh giá bằng kết quả thực tế và được cải tiến liên tục trong phát triển, vận hành thay vì dừng ở một tài liệu kế hoạch.


# Chủ sở hữu dữ liệu

Trong chương **Data protection**, **chủ sở hữu dữ liệu** (*data owner*) là vai trò chịu trách nhiệm quản trị một tập dữ liệu hoặc miền dữ liệu trong tổ chức: xác định mục đích và giá trị sử dụng, mức độ nhạy cảm, yêu cầu bảo vệ, quyền truy cập hợp lệ, thời hạn lưu giữ, cách chia sẻ và các quyết định rủi ro thuộc thẩm quyền. Data owner phải bảo đảm có người vận hành kiểm soát và có bằng chứng để kiểm tra các yêu cầu đã được đáp ứng.

Ví dụ, nền tảng học trực tuyến lưu thông tin học viên, bài nộp, kết quả học tập và lịch sử thanh toán. Backend có thể do đội Engineering vận hành, cơ sở dữ liệu do DBA quản lý, còn quyền quyết định ai được dùng kết quả học tập để chấm điểm, phân tích hay xuất cho đối tác thuộc trách nhiệm quản trị nghiệp vụ được giao. **Người có quyền quản trị database không tự trở thành người được phép định đoạt mọi cách sử dụng dữ liệu trong database đó.**

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là đánh giá có bằng chứng rằng hệ thống đáp ứng các mục tiêu bảo mật: từ phân tích rủi ro, security requirements và controls đến kiểm thử, audit, khắc phục finding và bảo đảm liên tục trong phát triển/vận hành. Vì thế, bài học không dừng ở việc gắn tên một cá nhân vào cột “Owner”. Cần đi tới câu hỏi: **Người chịu trách nhiệm đã được xác định đúng chưa; họ đã đưa ra yêu cầu bảo vệ có thể thực thi chưa; kiểm soát do các nhóm khác triển khai có hiệu quả không; và bằng chứng nào cho phép kết luận điều đó?**

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò **data owner** và phân biệt nó với data steward, data custodian, system owner, data product owner, risk owner và các vai trò bảo vệ dữ liệu cá nhân theo khung áp dụng.
2. Xác định **đối tượng sở hữu**, phạm vi, nguồn dữ liệu, mức phân loại, luồng chia sẻ và vòng đời của từng tập dữ liệu.
3. Giao accountability, quyền quyết định và trách nhiệm vận hành theo mô hình RACI phù hợp, tránh dữ liệu mồ côi hoặc nhiều người tự nhận có quyền quyết định cuối cùng.
4. Chuyển mục tiêu dữ liệu thành security requirements và controls đo được về truy cập, tính toàn vẹn, dữ liệu tối thiểu, mã hóa, lưu giữ, sao lưu, chia sẻ và hủy bỏ.
5. Hiểu giới hạn quyền của data owner: quyền phê duyệt nội bộ **không thay thế** nghĩa vụ pháp lý, không tự cấp quyền truy cập kỹ thuật và không xóa rủi ro đã được chứng minh.
6. Thiết kế ma trận **risk → data owner decision → control → test/evidence → assurance conclusion**.
7. Lập data ownership register và hồ sơ evidence có owner, nguồn, phiên bản, thời kỳ, phạm vi, điều kiện chấp nhận và lịch tái đánh giá.
8. Xử lý các tình huống về dữ liệu phái sinh, data lake, dữ liệu dùng chung, chuyển hệ thống, bên thứ ba, incident và quyền truy cập khẩn cấp.
9. Phân biệt **control failure**, **evidence gap**, ngoại lệ và residual risk để báo cáo trung thực.

## 2. Chủ sở hữu dữ liệu là gì?

### 2.1. Một vai trò accountability, không phải quyền chiếm hữu tuyệt đối

**Data owner** thường là vai trò nghiệp vụ hoặc quản trị được tổ chức giao trách nhiệm đối với một miền/tập dữ liệu. Data owner quyết định hoặc tham gia quyết định trong thẩm quyền về:

- Dữ liệu được thu thập và dùng cho **mục đích** nào.
- Dữ liệu được **phân loại** theo tác động khi lộ, sai lệch hoặc không sẵn sàng ra sao.
- Những nhóm chủ thể nào **cần truy cập**, vì mục đích gì và trong điều kiện nào.
- Dữ liệu nào có thể **chia sẻ với hệ thống, tổ chức hoặc nhà cung cấp** khác.
- Các yêu cầu về **chất lượng, tính toàn vẹn, khả dụng và thời gian lưu giữ**.
- Những control nào phải được triển khai để đáp ứng rủi ro và nghĩa vụ.
- Khi phát sinh thay đổi hoặc sự cố, ai phải đánh giá tác động và cập nhật quyết định.
- Evidence và báo cáo nào cần để kiểm tra mức bảo đảm.

Từ “sở hữu” trong quản trị dữ liệu **không đồng nghĩa quyền sở hữu tài sản tuyệt đối theo pháp luật**. Không nên suy ra data owner là người có thể bán, công khai, xóa hoặc xử lý dữ liệu cá nhân theo ý muốn. Quyền của người có dữ liệu, nghĩa vụ của tổ chức và điều khoản hợp đồng vẫn áp dụng theo phạm vi pháp lý liên quan.

### 2.2. “Sở hữu” phạm vi gì?

Đơn vị quản trị có thể là:

- **Data domain:** thông tin học viên, dữ liệu chấm điểm, dữ liệu thanh toán.
- **Dataset/data product:** bảng học viên, báo cáo tiến độ, data mart cho phân tích.
- **Data element nhạy cảm:** mã định danh, thông tin liên hệ, trường dữ liệu hạn chế.
- **Data flow/use case:** luồng xuất file, tích hợp với SaaS phân tích, pipeline machine learning.
- **Derived data:** bộ chỉ số, bản tổng hợp hoặc tập dự đoán được tạo từ dữ liệu nguồn.

Thường nên xác định accountability ở **data domain**, sau đó bổ sung owner/đầu mối ở dataset và quy tắc quyền với data elements hoặc use cases nhạy cảm. Không bắt buộc mỗi cột phải có một data owner riêng, nhưng các tình huống dữ liệu được sử dụng theo mục đích mới phải có người chịu trách nhiệm được xác định.

### 2.3. Một người có thể giữ nhiều vai trò nhưng trách nhiệm phải phân biệt

Ở tổ chức nhỏ, Product Manager có thể vừa là business owner, data owner và risk owner trong phạm vi được ủy quyền. Tuy nhiên cần ghi rõ **họ quyết định điều gì, control nào do đội khác vận hành và ai đánh giá độc lập**. Không nên mặc định người sở hữu dữ liệu tự cho rằng control đã đạt chỉ vì họ phê duyệt kế hoạch.

## 3. Data owner khác các vai trò liên quan

| Vai trò | Trọng tâm | Quyết định hoặc hoạt động điển hình | Không được tự suy ra |
|---|---|---|---|
| **Data owner** | Accountability đối với giá trị, mục đích, quy tắc và rủi ro của data domain | Phê duyệt phạm vi sử dụng/chia sẻ, phân loại, yêu cầu bảo vệ, review quyền | Không mặc nhiên là DBA hay người sở hữu pháp lý của mọi bản ghi |
| **Data steward** | Chăm sóc định nghĩa, metadata, chất lượng và quy trình dữ liệu hằng ngày | Duy trì data dictionary, lineage, quality rules, hỗ trợ phân loại | Không tự quyết định ngoại lệ bảo mật vượt thẩm quyền |
| **Data custodian** | Bảo quản và vận hành kỹ thuật đối với dữ liệu/hạ tầng | Backup, storage, encryption config, quyền DB, logging | Không mặc nhiên có quyền dùng dữ liệu cho mục đích khác |
| **System/application owner** | Hệ thống xử lý/lưu dữ liệu hoạt động đúng yêu cầu | Triển khai app controls, release, availability và incident response | Không tự quyết định mọi policy nghiệp vụ của dữ liệu đi qua hệ thống |
| **Data product owner** | Giá trị và vòng đời của sản phẩm dữ liệu | Chất lượng, SLA, người sử dụng, version/data contract | Không tự thay thế data owner gốc hoặc nghĩa vụ privacy |
| **Information/security owner** | Một vai trò có thể được tổ chức định nghĩa gần data owner | Phân loại và control yêu cầu theo chính sách | Không nên coi tên vai trò giống nhau ở mọi tổ chức |
| **Risk owner** | Chịu trách nhiệm phương án xử lý residual risk theo ủy quyền | Chấp nhận, giảm thiểu, tránh/chuyển rủi ro trong thẩm quyền | Không đồng nghĩa mọi data owner có quyền chấp nhận risk vượt ngưỡng |
| **Security/GRC/CISO** | Thiết lập policy, hỗ trợ risk assessment, đánh giá và giám sát | Baseline, assurance, finding, escalation | Không tự thay business owner quyết định mục đích sử dụng dữ liệu |
| **Privacy/Legal/DPO khi áp dụng** | Diễn giải và giám sát nghĩa vụ dữ liệu cá nhân theo tổ chức/pháp luật | Tư vấn vai trò, mục đích, thời hạn, quyền chủ thể dữ liệu | Không được đánh đồng DPO với data owner hoặc data controller |
| **Data subject** | Cá nhân mà dữ liệu cá nhân liên quan tới | Thực hiện các quyền được pháp luật áp dụng bảo vệ | Không phải “data owner” nội bộ theo nghĩa RACI |
| **Data controller/processor** | Vai trò pháp lý về quyết định mục đích/phương tiện và xử lý dữ liệu theo khung cụ thể | Phân chia trách nhiệm và nghĩa vụ với đối tác | Không nên dịch một-một thành data owner/data custodian |
| **Assessor/auditor** | Kiểm chứng các claim/control trong phạm vi được giao | Đánh giá evidence, test, báo finding | Không tự chuyển kết quả fail thành pass vì owner đồng ý |

**Một ranh giới rất quan trọng:** trong các khung pháp luật về dữ liệu cá nhân, *controller* và *processor* là những vai trò pháp lý có định nghĩa và hệ quả riêng, có thể thay đổi theo pháp luật và hoạt động xử lý. **Data owner** ở đây là chức danh quản trị nội bộ. Hai hệ thống vai trò có thể liên quan nhưng không thay thế nhau.

### 3.1. Tình huống minh họa

Nền tảng học thuê một nhà cung cấp cloud để lưu cơ sở dữ liệu điểm:

- Academic Business Owner có thể là **data owner** của kết quả học tập.
- DBA/Cloud Platform là **data custodian** trong phạm vi vận hành kỹ thuật.
- Learning API team là **application owner** của luồng đọc/sửa điểm.
- Privacy/Legal đánh giá **nghĩa vụ** khi dữ liệu cá nhân được xử lý.
- Risk owner phê duyệt rủi ro còn lại theo **thẩm quyền**.
- Cloud provider có **trách nhiệm dịch vụ riêng** được xác định theo hợp đồng và mô hình shared responsibility.

Nếu data owner phê duyệt cho một nhóm giảng viên xem điểm, backend vẫn phải kiểm tra **quyền theo từng lớp/học viên**, không chỉ gán một quyền đọc toàn DB cho nhóm giảng viên.

## 4. Vì sao dữ liệu phải có owner được chỉ định rõ?

### 4.1. Dữ liệu không có owner gây lỗ hổng ra quyết định

Khi không ai chịu trách nhiệm:

- Dữ liệu được giữ “để sau này có thể dùng” mà không có mục đích, kỳ lưu hoặc phân loại.
- Nhân sự IT không biết ai có thể phê duyệt truy cập đến hồ sơ nhạy cảm.
- Quyền đã cấp không được rà soát sau khi người dùng chuyển vị trí.
- File xuất và dataset phái sinh tiếp tục nằm trong object storage mà không có kế hoạch xóa.
- Bộ dữ liệu được chia sẻ tới vendor dù chưa làm rõ giới hạn dữ liệu và nghĩa vụ.
- Sự cố ảnh hưởng dữ liệu không có người xác định tác động, ưu tiên và nguồn liên lạc.
- Audit thu thập được cấu hình nhưng không có tiêu chí nghiệp vụ để kết luận “đúng quyền”.

### 4.2. Owner không rõ dẫn đến trách nhiệm chồng chéo

Một data lake có dữ liệu học viên, thanh toán và hỗ trợ khách hàng. Nếu đội Data Engineering được coi là “owner mọi dữ liệu” vì họ vận hành pipeline, họ có thể bị buộc quyết định những vấn đề **thuộc mục đích và mức độ nhạy cảm nghiệp vụ** mà họ không có thẩm quyền. Ngược lại, nếu Product tự nhận owner thì có thể bỏ sót trách nhiệm vận hành và privacy.

Giải pháp là **tách data ownership khỏi custody, system ownership và pháp lý**, đồng thời định rõ người có trách nhiệm cuối cùng đối với từng loại quyết định.

### 4.3. Owner là điều kiện hỗ trợ assurance

Một auditor có thể hỏi: “Tại sao nhóm hỗ trợ được đọc thông tin liên hệ học viên?” Câu trả lời đáng tin phải truy vết đến:

1. **Mục đích và yêu cầu nghiệp vụ** được data owner xác lập.
2. **Data classification** và nghĩa vụ áp dụng.
3. **Quy tắc quyền** theo vai trò, hành động, đối tượng, thời gian.
4. **Approval và provisioned entitlement** theo đúng quy trình.
5. **Actual runtime control** được triển khai.
6. **Test/log/review evidence** cho thấy control hoạt động.
7. **Exception/risk record** nếu có trường hợp sai lệch.

Một tên owner trong Excel mới chỉ hỗ trợ bước đầu, chưa chứng minh sáu bước tiếp theo.

## 5. Nền tảng của data ownership: mục tiêu, dữ liệu, rủi ro

Data owner cần hiểu **dữ liệu của mình** trước khi đưa ra yêu cầu bảo vệ.

### 5.1. Bộ câu hỏi nhận diện

1. Dữ liệu biểu diễn điều gì, được tạo và thu thập từ đâu?
2. Ai là người tạo, ai là người dùng hợp lệ, ai có thể bị tác động?
3. Dữ liệu có chứa thông tin cá nhân, bí mật kinh doanh, kết quả học tập hoặc thông tin bảo mật hệ thống không?
4. Dữ liệu ảnh hưởng **confidentiality, integrity, availability** như thế nào?
5. Dữ liệu có được tổng hợp, suy luận, chuyển đổi, đào tạo mô hình hoặc tái sử dụng không?
6. Đi qua những hệ thống, tenant, service, storage, backup, data lake, đối tác nào?
7. Cần dữ liệu bao lâu, khi nào archive hoặc xóa?
8. Một thay đổi sai có thể gây hậu quả gì cho người dùng, vận hành và nghĩa vụ hợp đồng?
9. Ai quyết định chia sẻ và ai thực thi quyền?
10. Những thông tin nào vẫn chưa rõ và cần điều tra trước khi phê duyệt?

### 5.2. Data ownership khác risk ownership như thế nào?

Data owner chịu trách nhiệm **làm rõ yêu cầu và tác động đối với dữ liệu**. Người có thẩm quyền chấp nhận residual risk có thể là data owner hoặc một cấp khác, tùy risk governance.

Ví dụ, data owner có thể đánh giá rằng chia sẻ hồ sơ học viên sang hệ thống phân tích mới làm tăng tác động lộ dữ liệu. Nếu rủi ro vượt ngưỡng được ủy quyền, không được tự chấp nhận chỉ vì họ là owner của dataset; cần **escalation** lên đúng cấp và tham vấn Privacy/Legal khi áp dụng.

### 5.3. CIA và ngoài CIA

| Thuộc tính | Data owner cần xác định | Ví dụ |
|---|---|---|
| **Confidentiality** | Ai được biết dữ liệu và giới hạn tiết lộ | Điểm cá nhân không hiển thị cho người không có quyền |
| **Integrity** | Điều gì làm dữ liệu đúng và ai được phép thay | Chỉ giảng viên được phân công sửa điểm theo quy trình |
| **Availability** | Dữ liệu cần sẵn sàng khi nào; khôi phục ở mức nào | Lịch thi hoặc điểm phải truy cập được trong kỳ công bố |
| **Authenticity/provenance** | Có kiểm tra nguồn tạo/sửa và nguồn hệ thống không | Điểm được tạo qua quy trình chấm được kiểm soát |
| **Accountability** | Có thể truy vết thay đổi và quyết định quan trọng không | Ghi ai sửa điểm, thời điểm, lý do, approval |
| **Privacy/purpose limitation** | Dữ liệu cá nhân được xử lý đúng mục đích và điều kiện | Không tự dùng bài nộp để huấn luyện mô hình mới |
| **Data quality/fitness for use** | Quy tắc đầy đủ, đúng định dạng, kịp thời và nhất quán | Điểm tổng hợp không chứa bản ghi trùng hoặc sai học kỳ |
| **Resilience** | Giữ khả năng phục hồi và di chuyển khi phụ thuộc thất bại | Có restore test cho bảng điểm và file bài nộp |

**Security assurance** chủ yếu đánh giá các mục tiêu bảo vệ và controls, nhưng có thể cần bằng chứng về chất lượng/lineage vì dữ liệu sai ảnh hưởng tính toàn vẹn và quyết định nghiệp vụ.

## 6. Phân loại dữ liệu là trách nhiệm quản trị quan trọng

### 6.1. Classification có mục tiêu gì?

Phân loại giúp lựa chọn kiểm soát tương xứng với tác động khi mất bảo mật. Các cấp có thể được tổ chức tự đặt, ví dụ:

| Cấp minh họa | Đặc điểm | Cách xử lý dự kiến |
|---|---|---|
| **Public** | Đã được phê duyệt công khai | Kiểm soát tính toàn vẹn và thẩm quyền công bố |
| **Internal** | Phục vụ công việc nội bộ, lộ có thể gây ảnh hưởng hạn chế | Truy cập theo nhu cầu, kiểm soát chia sẻ |
| **Confidential** | Thông tin nhạy cảm hoặc có tác động đáng kể nếu tiết lộ | Scope quyền cụ thể, bảo vệ lưu/truyền, audit phù hợp |
| **Restricted** | Dữ liệu/tài sản có tác động nghiêm trọng nếu bị lộ hoặc thay đổi | Controls mạnh hơn theo baseline, review kỹ, giới hạn xuất và giám sát |

Đây là **ví dụ classification scheme nội bộ**, không phải nghĩa vụ phân loại chung do một chuẩn quy định cho mọi tổ chức. Một tập dữ liệu có thể có nhiều chiều như mức bí mật, yêu cầu tính toàn vẹn, thời gian phục hồi và cờ dữ liệu cá nhân.

### 6.2. Data owner làm gì?

- Xác định ý nghĩa/tác động nghiệp vụ của dữ liệu.
- Đề xuất hoặc phê duyệt classification theo chính sách được giao.
- Đối chiếu dữ liệu thực tế với metadata/data dictionary.
- Ghi quy tắc chia sẻ và biện pháp tối thiểu được áp dụng.
- Yêu cầu kiểm tra lại khi dữ liệu mới, mục đích mới hoặc công nghệ xử lý mới xuất hiện.
- Bảo đảm quyền phân loại **không vượt** các điều kiện bắt buộc của pháp luật/hợp đồng.

### 6.3. Khi một dataset có nhiều loại dữ liệu

Một file export kết hợp điểm học viên, email, tên và ghi chú hỗ trợ có thể có tác động cao hơn từng trường riêng. Data owner và Privacy/Security cần xác định **classification của kết quả kết hợp**, tránh tự xem từng trường là “ít nhạy cảm” rồi cho phép xuất toàn bộ.

Một tập thống kê được gọi là “ẩn danh” chưa chắc không thể tái nhận dạng nếu có trường định danh gián tiếp, bộ lọc quá nhỏ hoặc dữ liệu phụ trợ. Muốn giảm mức phân loại cần căn cứ phương pháp và đánh giá phù hợp; **đổi tên trường hoặc hash ID không tự tạo dữ liệu ẩn danh**.

## 7. Data inventory và data catalog có owner

### 7.1. Danh mục tối thiểu

Một data ownership register có thể ghi:

- **Data domain ID**, dataset ID, tên và mô tả.
- **Data owner** chịu trách nhiệm cuối, người thay thế và cách liên hệ theo chức danh.
- **Data steward/custodian/system owner** và các team kỹ thuật liên quan.
- **Source of truth** và nguồn dữ liệu phát sinh.
- **Data classification** và loại dữ liệu cá nhân/nhạy cảm nếu có.
- **Business purposes** được phê duyệt; những cách sử dụng bị cấm hoặc cần review.
- **System/tenant/environment** lưu hoặc xử lý; vị trí data lake, object storage, backup.
- **Data subjects** hoặc đối tượng bị ảnh hưởng khi thích hợp.
- **Data consumers, recipients, vendors/subprocessors** quan trọng.
- **Retention, archival, deletion rules** và nghĩa vụ liên quan.
- **Access policy**, control mappings và kiểm thử quan trọng.
- **Owner review date, change triggers, approvals, exceptions, findings**.

Không nên đưa secret hoặc toàn bộ PII vào catalog chỉ để định nghĩa ownership. Catalog nên mô tả metadata và tham chiếu nguồn dưới quyền phù hợp.

### 7.2. Những dataset mồ côi

Dataset mồ côi là tập dữ liệu không có owner chịu trách nhiệm rõ hoặc owner đã rời vai trò nhưng chưa có người thay. Có thể phát hiện từ catalog, storage inventory, data warehouse queries, ETL pipeline, repository và chi phí cloud.

Khi phát hiện:

1. Xác định hệ thống nguồn, nội dung, tính nhạy cảm và đường truy cập.
2. Chỉ định **interim custodian/quarantine owner** và giới hạn truy cập nếu cần.
3. Tìm business domain và cấp quản lý có quyền chỉ định data owner.
4. Ghi quyết định, phân loại, retention và quyền đang tồn tại.
5. Rà soát các đối tượng đã dùng dữ liệu trong giai đoạn thiếu owner.
6. Đưa dataset vào chương trình review hoặc ngừng/xóa theo quy trình nếu không còn mục đích hợp lệ.

Không nên xóa dữ liệu không có owner ngay khi phát hiện mà chưa xem **tính toàn vẹn nghiệp vụ, nghĩa vụ lưu giữ, backup và điều tra**.

### 7.3. Ai là owner của dữ liệu dẫn xuất?

Ví dụ Learning Analytics tạo **chỉ số nguy cơ bỏ học** từ lịch sử học và dữ liệu chấm điểm. Dữ liệu dẫn xuất có thể bộc lộ thông tin nhạy cảm mới. Có thể cần một data product owner cho kết quả phân tích, nhưng ownership của nguồn và trách nhiệm pháp lý liên quan **không biến mất** chỉ vì đã ETL sang bảng khác.

Chính sách nên quy định cách kế thừa **classification, use restrictions, retention và approval**, đồng thời có review khi mục đích xử lý thay đổi.

## 8. Data flow, lineage và ranh giới tin cậy

Không thể phê duyệt bảo vệ dataset nếu không biết nó đi đâu.

### 8.1. Data flow mẫu

~~~mermaid
flowchart LR
    L["Học viên/giảng viên"] --> API["Learning Java API"]
    API --> DB[("Operational Database")]
    DB --> EVT["Event/ETL Pipeline"]
    EVT --> DW[("Analytics Warehouse")]
    DW --> SAAS["Analytics Vendor"]
    API --> JOB["Export Queue/Worker"]
    JOB --> OBJ[("Private Object Storage")]
    DB --> BAK[("Protected Backup")]
    API --> LOG["Audit Logging"]
    OBJ --> LOG
~~~

Data owner cần nhận diện:

- Những **điểm tạo/sửa** dữ liệu chính thức.
- Nơi dữ liệu có thể **nhân bản, cache, xuất, sao lưu, tổng hợp hoặc biến đổi**.
- Những **trust boundaries**: client–server, tenant, ứng dụng–worker, tổ chức–vendor.
- Ai thực thi **object-level authorization**, ai quản lý key/storage, ai chịu trách nhiệm xóa.
- Khi thay đổi mục đích dùng, **quy trình phê duyệt** nào bị kích hoạt.
- Nếu dữ liệu nguồn bị sửa, các bản dẫn xuất có cập nhật đúng và truy vết được không.

Sơ đồ dòng dữ liệu hỗ trợ threat modeling; nó **không tự chứng minh** security controls đang chạy đúng. Phải đối chiếu với runtime configuration, pipeline inventory, quyền, test và log.

### 8.2. Lineage và trách nhiệm

**Data lineage** mô tả các quan hệ nguồn, biến đổi, vị trí và đích của dữ liệu. Nó giúp đánh giá tác động: “Nếu phát hiện một file điểm được truy cập trái quyền, những downstream dataset và nhà cung cấp nào cũng đã nhận bản sao?”

Chủ sở hữu dữ liệu thường cần trả lời **vì sao dùng, có được dùng không và tác động gì**, còn data steward/custodian/engineering cung cấp **bằng chứng đường đi thực tế và các biện pháp**.

### 8.3. Snapshot không thay bằng chứng qua thời kỳ

Một sơ đồ kiến trúc được duyệt cách đây hai quý có thể không liệt kê vendor mới, pipeline batch cũ hoặc object storage được thêm gần đây. Cần quản lý **phiên bản data flow**, trigger review khi thay đổi và đối chiếu đường thực tế theo mức rủi ro.

## 9. Quy trình giao và chuyển data ownership

### 9.1. Giao theo data domain và thẩm quyền

Một quy trình đề xuất:

1. Nhận diện **data domain/dataset và mục đích sử dụng**.
2. Xác định đơn vị nghiệp vụ có thẩm quyền đưa ra quyết định.
3. Chỉ định **một accountable data owner** cho mỗi quyết định quan trọng, có người thay khi vắng mặt.
4. Ghi ranh giới với system owner, data steward, IT custodian và Privacy/Security.
5. Xác nhận classification, access policy, data quality, retention và cách xử lý risk.
6. Gán nguồn evidence, lịch review và trigger thay đổi.
7. Tạo data register, lưu phiên bản và thông báo các team thực thi.
8. Khi ownership thay, bàn giao cả **open findings, exceptions, approvals, vendor data flows và pending decisions**.

Một người có thể là owner của nhiều dataset; không cần tạo số lượng chức danh quá lớn. Điều quan trọng là **không để quyết định trọng yếu vô chủ**.

### 9.2. Trường hợp có hai đơn vị cùng sử dụng

Bộ phận Đào tạo sở hữu quy tắc dùng điểm; bộ phận Chăm sóc học viên muốn xem một phần dữ liệu để hỗ trợ. Không nhất thiết cả hai trở thành đồng owner ngang nhau của dataset. Có thể xác định:

- **Accountable data owner** của domain điểm.
- **Consumer/business purpose owner** cho quy trình hỗ trợ.
- **Custodian/Engineering** triển khai giới hạn trường và quyền.
- **Privacy/Legal** xem mục đích, cơ sở xử lý và nghĩa vụ.
- **Risk owner** quyết định ngoại lệ/residual risk theo ủy quyền.

Nếu tổ chức lựa chọn đồng sở hữu ở cấp liên phòng ban, phải chỉ rõ **cơ chế giải quyết xung đột, người duyệt cuối và quyền escalation**; không chấp nhận “ai cũng có quyền duyệt” khiến không ai chịu trách nhiệm.

### 9.3. Ownership thay đổi theo sản phẩm

Khi một nhóm sản phẩm giải thể hoặc tập dữ liệu chuyển sang một đơn vị, cần bàn giao **quyền quyết định và nghĩa vụ**, không chỉ đổi email của owner trong catalog. Kiểm tra các lịch review, SLO dữ liệu, retention, dữ liệu chia sẻ, các quyền phê duyệt trước đó và những finding chưa đóng.

## 10. RACI cho vòng đời dữ liệu

R = thực hiện, A = accountable theo ủy quyền, C = tham vấn, I = được thông báo.

| Hoạt động | Data owner | Data steward | Custodian/Engineering | Security/GRC | Privacy/Legal | Risk owner |
|---|---|---|---|---|---|---|
| Mục đích và phạm vi sử dụng | A/R | C | C | C | C | I |
| Phân loại dữ liệu theo policy | A | R hỗ trợ | C | C | C | I |
| Thiết kế schema, lineage, metadata | C | A/R cho governance được giao | R kỹ thuật | C | C | I |
| Đặt yêu cầu truy cập nghiệp vụ | A/R | C | C | C | C | I |
| Triển khai authorization/IAM | C | C | A/R | C | I | I |
| Review truy cập theo owner | A/R về nhu cầu nghiệp vụ | R điều phối | R cung cấp quyền thực tế | C | C | I |
| Thiết kế/kiểm tra encryption, backup | C về mục tiêu | I | A/R | C | C | I |
| Chia sẻ dữ liệu sang vendor | A về mục đích và phạm vi | R điều phối | R tích hợp | C | C về nghĩa vụ | I hoặc A khi cần risk decision |
| Quyết định residual risk vượt baseline | C hoặc R đề xuất | C | C | C | C | A |
| Khắc phục finding kỹ thuật | C về impact/priorities | R quản lý metadata | A/R với hệ thống liên quan | C/retest | C khi áp dụng | I |
| Kết luận assurance độc lập | C | C | C | A/R hoặc assessor riêng | C | I |
| Archive/delete theo nghĩa vụ | A về chính sách/mục đích | R theo dõi | R thực thi | C | C | I |

Bảng là **ví dụ**, không phải yêu cầu chung của một tiêu chuẩn. Tổ chức phải xác định một người hoặc cấp **A** rõ cho từng hoạt động thực tế. Khi security assurance được đánh giá độc lập, người lập control và người kết luận về control không nên bị coi mặc nhiên là cùng một vai trò.

## 11. Quyền phê duyệt truy cập không đồng nghĩa quyền thực thi

### 11.1. Quyết định nghiệp vụ và security enforcement

Một data owner có thể phê duyệt nhu cầu: “giảng viên của lớp 42 được xem bảng điểm lớp 42 để chấm và công bố”. Engineering phải chuyển nó thành **authorization rules** tại backend, worker và nơi tải file, còn IAM team có thể cấp những nhóm quyền liên quan.

**Data owner không nên tự cấp direct database admin access** cho người dùng cuối nếu không được ủy quyền và không đi qua policy. Một email “data owner đồng ý” chỉ là phần approval, không phải bằng chứng runtime access an toàn.

### 11.2. Decision matrix

| Actor | Action | Data object | Điều kiện cho phép | Điều phải từ chối |
|---|---|---|---|---|
| Học viên A | Xem điểm | Điểm của A | Account hợp lệ, dữ liệu được công bố theo quy tắc | Điểm của học viên khác |
| Giảng viên lớp 42 | Nhập điểm | Lớp 42 | Được phân công và còn trong thời gian được phép | Lớp 43 hoặc lớp đã khóa |
| Nhân sự hỗ trợ | Xem contact | Hồ sơ liên hệ trong scope hỗ trợ | Có nhiệm vụ được phân công, trường dữ liệu được phép | Điểm/ghi chú hạn chế nếu không có quyền |
| Report worker | Đọc dữ liệu | Dataset đã được duyệt trong export job | Job có scope xác minh và worker enforcement | Đọc lớp ngoài scope |
| Data analyst | Dùng dữ liệu | Dataset tổng hợp được duyệt | Mục đích và thời hạn phù hợp, truy cập có kiểm soát | Truy xuất raw PII nếu không cần |
| Vendor | Nhận sự kiện | Trường dữ liệu hợp đồng cho phép | API token giới hạn scope, điều khoản cần thiết | Dữ liệu khác hoặc xử lý mục đích mới |
| Platform admin | Quản lý hạ tầng | Storage/DB | Theo nhiệm vụ và privileged process | Dùng dữ liệu cho mục đích cá nhân hoặc vượt nhiệm vụ |

Chính sách của data owner cung cấp **đầu vào** cho quy tắc quyền; application authorization phải thực thi từ **nguồn danh tính/quyền đáng tin**, không từ một tham số do client tự khai.

### 11.3. Review quyền đang tồn tại

Một approval khi cấp quyền **không có giá trị vô hạn**. Data owner hoặc người được giao phải xem quyền còn phù hợp mục đích, dữ liệu và thời gian không; custodian cung cấp **effective permissions**, access history và các grants từ group, local account, cloud role hoặc SaaS. Thời điểm review dựa trên phân loại và biến động quyền.

Nếu data owner xác nhận “không còn nhu cầu” nhưng IAM chưa thu hồi, control chưa đạt **implementation/operating requirement**. Cần target acknowledgment và phép kiểm tra không còn quyền.

## 12. Data owner và yêu cầu bảo vệ tính bí mật

### 12.1. Những rủi ro cần nghĩ tới

- **Truy cập chéo đối tượng/tenant** qua API.
- **Báo cáo quá rộng** xuất dữ liệu của nhiều lớp.
- **Chia sẻ link file** ngoài phạm vi cho phép.
- **Quyền người vận hành/vendor** vượt mục đích công việc.
- **Đưa dữ liệu nhạy cảm vào log, cache hoặc hệ thống analytics**.
- **Xuất dữ liệu sang môi trường thử nghiệm** không được bảo vệ tương ứng.
- **Lộ bản sao backup hoặc dữ liệu giữ lâu**.
- **Khả năng tái nhận dạng dữ liệu tổng hợp** nếu thiết kế ẩn danh không đủ.

### 12.2. Requirements có thể kiểm chứng

Một data owner có thể yêu cầu:

1. Chỉ role và quan hệ nghiệp vụ có thẩm quyền mới truy cập dữ liệu đã phân loại.
2. Authorization phải kiểm tra **actor + action + object + tenant + trạng thái** tại server.
3. Các bộ dữ liệu xuất phải chứa **trường tối thiểu** cho mục đích đã phê duyệt.
4. File/bản sao trong storage không thể đọc qua đường ngoài quyền.
5. Có logging/audit thích hợp cho hành vi nhạy cảm, không lưu secret hoặc PII quá mức.
6. Quyền người dùng, vendor và service identities được review theo rủi ro.
7. Token, secret, dữ liệu truyền/lưu được bảo vệ phù hợp với classification.
8. Có khả năng thu hồi quyền hoặc ngắt luồng chia sẻ khi xảy ra sự cố.

Mỗi yêu cầu cần **control owner, nơi thực thi, test, evidence và tiêu chí**. Một dòng “Dữ liệu Confidential phải được bảo vệ” chưa đủ nếu không biết cấu hình nào cần kiểm tra và bằng cách nào.

## 13. Data owner và yêu cầu tính toàn vẹn, độ tin cậy dữ liệu

Không phải mọi rủi ro dữ liệu đều là lộ thông tin. Thay đổi điểm sai có thể làm mất quyền lợi học viên ngay cả khi không ai truy cập trái phép.

### 13.1. Các câu hỏi bảo vệ integrity

- Ai là nguồn **chính thức** cho một giá trị?
- Quy tắc nghiệp vụ nào quyết định dữ liệu **hợp lệ**?
- Người nào được **thay đổi** và lúc nào?
- Có cần approval, chữ ký hoặc đối soát đối với thao tác trọng yếu?
- Nếu nhiều service cùng ghi, xung đột và thứ tự được xử lý thế nào?
- Có kiểm soát migration, batch processing, ETL và replay/duplicate?
- Có log trước/sau, version và khả năng truy vết nguồn thay đổi?
- Có cách phát hiện, sửa, thông báo hoặc rollback khi dữ liệu sai?

### 13.2. Integrity controls không chỉ là validation

Ví dụ kết quả học tập:

| Risk | Control gợi ý | Verification |
|---|---|---|
| Sinh viên tự gửi request sửa điểm | Authorization và workflow checks | Negative tests và DB side effects |
| Nhập điểm ngoài kỳ cho phép | State machine và policy thời điểm | Boundary tests, approval records |
| ETL nhân đôi record điểm | Idempotency và khóa định danh thích hợp | Reconciliation, duplicate tests |
| Có hai bản điểm mâu thuẫn | Source of truth và version/lineage | Before/after checks, comparison |
| Migration làm mất một số học viên | Migration integrity checks | Row-level counts, sampling, checksum có scope |
| Admin sửa điểm và xóa audit | Phân nhiệm vụ, audit protection | Privileged tests, log integrity check |

Một data owner có thể **đặt tiêu chí nghiệp vụ** (“không một điểm chính thức nào được đổi mà không có dấu vết và thẩm quyền”), nhưng code, database constraints và telemetry phải do nhóm kỹ thuật triển khai/đánh giá.

## 14. Availability, backup và disaster recovery dưới góc data ownership

Data owner cần biết **tác động nếu dữ liệu không sẵn sàng** và mức khôi phục hợp lý. Sự thành công của backup job không tự chứng minh một tập dữ liệu quan trọng có thể phục hồi đầy đủ.

### 14.1. Những quyết định cần có

- Dữ liệu nào **critical**, phụ thuộc nghiệp vụ nào cần nó?
- Mục tiêu **RPO** (độ mất dữ liệu có thể chấp nhận) và **RTO** (thời gian phục hồi mục tiêu) theo BIA/risk là gì?
- Có yêu cầu khôi phục đúng phiên bản, bảo toàn quan hệ, toàn vẹn và audit trail không?
- Các bản backup có đúng tập dữ liệu và key giải mã cần thiết không?
- Có trường hợp phải phục hồi do ransomware, mất vùng cloud hoặc lỗi người vận hành không?
- Ai phê duyệt việc khôi phục dữ liệu cũ nếu có nguy cơ ghi đè bản ghi mới?
- Dữ liệu đã hết retention cần xử lý thế nào trong backup?
- Những kịch bản nào đã được diễn tập và những gì chưa được chứng minh?

### 14.2. Bằng chứng cho claim

**Claim:** “Các kết quả học tập chính thức trong scope có khả năng khôi phục trong ngưỡng đã phê duyệt”.

**Evidence cần thiết:** danh mục dataset, RPO/RTO từ business owner, cấu hình backup, quyền và khóa, kết quả restore test, thời gian thực tế, đối chiếu tính đầy đủ/integrity của dữ liệu sau khôi phục, giới hạn điều kiện thử và finding.

Một snapshot backup thành công nhưng chưa có restore test chỉ hỗ trợ một phần của claim. Khi cần khôi phục thật, data owner làm rõ **điểm dữ liệu và mức độ mất mát chấp nhận được** trong thẩm quyền; Operations thực hiện theo runbook đã duyệt.

## 15. Mục đích sử dụng, retention và nghĩa vụ dữ liệu cá nhân

### 15.1. Data owner không thể tự cho phép mọi cách sử dụng

Với dữ liệu cá nhân, tổ chức có thể phải đáp ứng các điều kiện về tính hợp pháp, minh bạch, mục đích xử lý, giới hạn thu thập, bảo vệ, quyền của cá nhân và quản lý nhà cung cấp tùy **pháp luật, hợp đồng, loại dữ liệu và hoạt động xử lý**. Data owner là đầu mối nghiệp vụ, nhưng không thay vai trò pháp lý được xác định theo quy định áp dụng.

Ví dụ: Learning Product muốn chuyển bài luận tự do của học viên sang một công cụ phân tích AI để “cải thiện trải nghiệm”. Data owner của kết quả học tập phải xem:

1. Mục đích mới có nằm trong **mục đích được phê duyệt** hay không?
2. Cần toàn bộ văn bản gốc hay chỉ các đặc trưng/tổng hợp không nhận dạng?
3. Có dữ liệu cá nhân hoặc thông tin nhạy cảm chứa trong văn bản không?
4. Cơ sở/điều kiện xử lý, thông báo, hợp đồng và những quyền của chủ thể dữ liệu nào áp dụng?
5. Vendor lưu, sử dụng lại, huấn luyện, chia sẻ và xóa dữ liệu ra sao?
6. Có khả năng hủy xử lý hoặc thu hồi quyền trong trường hợp được yêu cầu?
7. Cần kiểm tra mô hình phái sinh, output và khả năng tái nhận dạng không?
8. Ai có thẩm quyền đưa quyết định sau privacy/security assessment?

Không nên gắn nhãn “analytics” rồi mặc định mọi dữ liệu có thể được dùng cho mọi mục tiêu. **Mỗi mục đích mới có thể làm thay đổi risk, legal requirements và control baseline.**

### 15.2. Retention schedule có owner

Thời hạn lưu giữ nên được xác định theo **mục đích, nghĩa vụ và nhu cầu nghiệp vụ thực**. Một record giữ vô hạn vì “có thể cần” làm tăng rủi ro trong môi trường production, data lake, log, backup và hệ thống vendor.

| Loại dữ liệu minh họa | Câu hỏi về retention | Vai trò phối hợp |
|---|---|---|
| Hồ sơ học viên đang theo học | Cần bao lâu để cung cấp dịch vụ? | Academic data owner, Privacy |
| Kết quả tốt nghiệp/chứng chỉ | Có nghĩa vụ lưu theo hồ sơ học vụ? | Data owner, Legal/Records Management |
| Log truy cập hồ sơ học viên | Cần cho điều tra/audit bao lâu, có quá nhiều PII không? | Security/SecOps, data owner, Privacy |
| File export tạm | Khi nào file và link tải hết nhu cầu? | Business owner, Platform |
| Bản backup | Chu kỳ lưu ảnh hưởng restore và khả năng xóa như thế nào? | Operations, Security, Privacy |
| Dữ liệu thử nghiệm | Có cần bản sao dữ liệu thật không? Khi nào xóa? | Engineering, data owner, Privacy |
| Dữ liệu ở vendor | Thời hạn, cơ chế xóa/hoàn trả và subprocessor? | Vendor owner, Legal/Privacy |
| Dataset phái sinh | Mục đích, tính nhạy cảm và thời gian tồn tại mới? | Data product owner, data owner nguồn |

Đây là nhóm **câu hỏi**, không phải bảng thời hạn bắt buộc. Tổ chức phải có quy tắc thực tế và **ghi phạm vi ngoại lệ** khi phải giữ bản sao do nghĩa vụ bắt buộc hoặc legal hold.

### 15.3. Retention khác deletion

Một bản ghi không còn được hiển thị trong ứng dụng chưa có nghĩa đã bị xóa ở warehouse, cache, vendor, log hoặc backup. Cần phân biệt:

- **Hết mục đích:** dữ liệu không còn cần dùng cho hoạt động ban đầu.
- **Archive:** chuyển sang phạm vi truy cập và mục đích khác có kiểm soát.
- **Retention obligation:** phải giữ dữ liệu theo điều kiện áp dụng, với quyền hạn chế.
- **Deletion/anonymization:** xóa hoặc chuyển đổi dữ liệu theo yêu cầu và phương pháp được phê duyệt.
- **Legal hold:** tạm ngừng việc xóa đối với dữ liệu xác định theo quy trình hợp lệ.

Data owner cần quyết định hoặc cung cấp căn cứ nghiệp vụ và phối hợp với người quản lý nghĩa vụ; **custodian thực thi và xác nhận kết quả**, assessor kiểm tra bằng chứng. Không tuyên bố “đã xóa mọi bản sao” chỉ từ một lệnh xóa bản ghi trong database.

## 16. Chia sẻ dữ liệu với đối tác và nhà cung cấp

### 16.1. Data sharing là một quyết định rủi ro có điều kiện

Một yêu cầu chia sẻ dữ liệu cần xem:

- **Ai nhận?** Tổ chức, vendor, subprocessor, người dùng trong tenant khác.
- **Vì sao cần?** Mục đích nghiệp vụ và giới hạn xử lý.
- **Dữ liệu nào?** Dataset, trường, độ chi tiết, phạm vi thời gian.
- **Bằng cách nào?** API, file transfer, stream, webhook, warehouse share.
- **Ở đâu và bao lâu?** Vùng lưu trữ/xử lý, thời gian giữ, backup.
- **Kiểm soát gì?** AuthN/AuthZ, encryption, minimization, logging, quota, incident contact.
- **Khi chấm dứt?** Ngắt truyền, revoke token, hoàn trả/xóa dữ liệu theo nghĩa vụ.
- **Ai quyết định?** Data owner, risk owner và Legal/Privacy theo phân quyền.

### 16.2. Data sharing agreement và hợp đồng

Bên nhận có thể cần những điều khoản như mục đích sử dụng, bảo mật, giới hạn quyền, nhà thầu phụ, thông báo sự cố, trợ giúp kiểm tra, thời hạn lưu, xóa và hỗ trợ chấm dứt. **Data owner nội bộ có thể xác nhận phạm vi được phép về nghiệp vụ**, nhưng không tự thay Procurement/Legal khi hợp đồng hoặc nghĩa vụ khác phải được đáp ứng.

Một thỏa thuận được ký chỉ chứng minh **cam kết**. Để đánh giá hiệu quả cần kiểm tra **payload thực**, OAuth/API scopes, cấu hình tenant, log truyền dữ liệu và evidence vendor trong phạm vi.

### 16.3. Ví dụ quyền OAuth quá rộng

Nhà cung cấp phân tích tiến độ học chỉ cần những trường đã tổng hợp, nhưng token được cấp quyền đọc toàn bộ hồ sơ học viên. Đây có thể là **control failure về least privilege** ngay cả khi vendor có báo cáo assurance tốt.

Các hành động cần xem:

1. Thu hẹp mục đích và data contract theo data owner.
2. Giới hạn API scope và tập dữ liệu ở source.
3. Kiểm thử token không đọc được đối tượng/endpoint ngoài scope.
4. Xem bản sao đã được truyền trước khi sửa quyền.
5. Ghi finding, impact, thời gian xử lý và retest.
6. Review quyền khi vendor có subprocessor/tính năng mới.

### 16.4. Chia sẻ dữ liệu không đồng nghĩa chuyển giao toàn bộ ownership

Đội Consumer Analytics có thể sở hữu dashboard và SLA dữ liệu phái sinh, nhưng vẫn cần tôn trọng **phân loại và giới hạn mục đích của nguồn**. Contract, data lineage và cơ chế xử lý khi data owner nguồn thay đổi policy cần được thiết kế trước, tránh xung đột khi dữ liệu đã nhân bản tới nhiều nhóm.

## 17. Dữ liệu phái sinh, data product và mô hình AI

### 17.1. Quyền quyết định ở mỗi tầng

Một pipeline:

~~~mermaid
flowchart LR
    A[("Điểm và tiến độ gốc")] --> B["ETL và kiểm tra dữ liệu"]
    B --> C[("Analytics dataset")]
    C --> D["Feature preparation"]
    D --> E["Mô hình dự đoán"]
    E --> F[("Dự đoán cho tư vấn học tập")]
    A -. "Data owner: học vụ" .-> O["Ownership và policy nguồn"]
    C -. "Data product owner" .-> P["Quality/SLA/mục đích phái sinh"]
    F -. "Business purpose owner" .-> Q["Quy tắc dùng kết quả"]
~~~

Sơ đồ chỉ minh họa cách chia trách nhiệm. **Không thể tự giả định** bản phái sinh ít nhạy cảm hơn nguồn; có trường hợp kết quả suy luận đưa ra thông tin nhạy cảm hoặc gây tác động lớn hơn.

### 17.2. Quy tắc cần xác định

- Data owner nguồn có quyền áp đặt **use restrictions** nào đối với bản phái sinh?
- Ai xác nhận mục đích mới và tác động đối với người bị ảnh hưởng?
- Dataset gốc thay hoặc phải xóa thì bản phái sinh và mô hình xử lý thế nào?
- Có kiểm tra provenance, chất lượng input, bias hoặc lỗi dự đoán liên quan không?
- Ai quyết định đưa kết quả dự đoán vào một hành động nghiệp vụ?
- Có giới hạn quyền với dữ liệu dùng để đào tạo, inference logs và model artifacts không?
- Khi dữ liệu tổng hợp bị tái nhận dạng hoặc trộn với nguồn khác, điều kiện bảo vệ nào được kích hoạt?

### 17.3. Data ownership không thể chuyển bằng tên folder

Nếu dataset được copy từ thư mục “academic” sang “analytics”, việc dữ liệu nằm trong storage do đội Analytics quản lý **không tự chuyển trách nhiệm nghiệp vụ/pháp lý**. Việc thay owner cần được ghi nhận theo policy, có chấp thuận và bàn giao các nghĩa vụ; lineage và metadata phải phản ánh nguồn và các thay đổi.

## 18. Data ownership trong SDLC và thay đổi kiến trúc

### 18.1. Thay đổi ứng dụng có thể làm đổi data risk

Mỗi lần thêm API, bảng dữ liệu, sự kiện, tính năng AI, export, vendor hay backup, cần xem **data owners nào bị ảnh hưởng**.

| Hoạt động | Câu hỏi của data owner | Bằng chứng cần liên kết |
|---|---|---|
| Thêm trường vào user profile | Trường mới có cần thiết và phù hợp mục đích không? | Data dictionary, privacy/security review |
| Mở API báo cáo mới | Ai được xem từng lớp/tenant/trường? | Authorization requirements, negative tests |
| Xây data lake | Dữ liệu nào được sao chép, ai quản lý lineage? | Data flow, data catalog, access design |
| Bổ sung event hoặc webhook | Payload có lộ PII không cần thiết? | Event schema, payload test, vendor scope |
| Migration dữ liệu | Có mất, trùng hoặc sai record không? | Mapping, counts, reconciliation, rollback |
| Mở môi trường thử nghiệm | Có dùng dữ liệu thật không, ai được phép? | Test-data policy, anonymization assessment |
| Sửa retention | Những bản sao/backup/vendor có áp dụng được không? | Retention schedule, deletion tests |
| Thay schema đánh giá học tập | Chỉ số nào là nguồn chính thức, ai duyệt? | Versioned data contract, quality checks |
| Thêm nhà cung cấp AI | Mục đích, dữ liệu, mô hình và nghĩa vụ mới? | Risk assessment, legal/privacy review, contractual requirements |

### 18.2. Data contract và control requirements

Một **data contract** có thể định nghĩa schema, owner, meaning, allowed consumers, classification, quality expectations, change compatibility và cách xử lý lỗi giữa producer và consumer. Data contract **không tự thay thế** contract pháp lý hoặc chính sách quyền truy cập; nó giúp kỹ thuật hóa những điều kiện mà data owner cần.

Ví dụ: thay đổi schema khiến dữ liệu “grade” từ trạng thái tạm thành chính thức mà không báo cho consumer có thể gây mất tính toàn vẹn nghiệp vụ. Cần approval/versioning và kiểm thử điều kiện downstream.

### 18.3. Điều kiện release liên quan đến data owner

Một release xuất dữ liệu nhạy cảm ra bên ngoài có thể cần chứng minh:

1. Data flow và purpose đã được review.
2. Phân loại được cập nhật khi có dữ liệu mới.
3. Authorization và data minimization đáp ứng tiêu chí.
4. Nghĩa vụ hợp đồng/privacy được xem xét khi áp dụng.
5. Đã có test và evidence gắn build/artifact/deployment.
6. Finding/risk còn lại được xử lý hoặc phê duyệt trong thẩm quyền.
7. Có logging, incident response, khả năng ngắt luồng và offboarding.

Không nên biến mọi thay đổi nhỏ thành một vòng phê duyệt thủ công nặng. Có thể đặt **risk-based triggers**: thay đổi mục đích hoặc recipients luôn cần review sâu hơn thay đổi format nội bộ không ảnh hưởng ngữ nghĩa/quyền.

## 19. Incident response: vai trò data owner khi có sự cố dữ liệu

### 19.1. Data owner đóng góp điều gì?

Khi có cảnh báo dữ liệu học viên bị truy cập sai:

- Xác định **tập dữ liệu và mức tác động nghiệp vụ**.
- Giải thích dữ liệu thuộc ai, mục đích, nhạy cảm và phạm vi sử dụng hợp lệ.
- Giúp xác định nhóm người và quy trình bị ảnh hưởng.
- Xác nhận mức ưu tiên đối với containment/khôi phục tính toàn vẹn.
- Phối hợp Privacy/Legal để hiểu nghĩa vụ áp dụng.
- Phối hợp Engineering và Incident Response xem downstream và bên thứ ba.
- Đề xuất các điều kiện khôi phục dịch vụ hoặc hạn chế export khi chưa đủ bằng chứng.
- Cập nhật data policy/controls sau bài học sự cố.

**Data owner không tự kết luận một sự kiện là “data breach” theo pháp luật** hoặc quyết định thông báo ra ngoài nếu chưa có thẩm quyền/chuyên môn liên quan. CISO/IR, Legal/Privacy và lãnh đạo có trách nhiệm theo quy trình được phê duyệt.

### 19.2. Sơ đồ phối hợp

~~~mermaid
flowchart TD
    A["Cảnh báo truy cập/sai lệch dữ liệu"] --> B["Security/IR xác minh dấu hiệu"]
    B --> C["Custodian/Engineering bảo vệ evidence, giới hạn tác động"]
    B --> D["Data owner xác định scope và impact"]
    D --> E["Privacy/Legal đánh giá nghĩa vụ khi áp dụng"]
    C --> F["Điều tra nguồn, bản sao, downstream"]
    E --> G["Quyết định thông báo/ứng phó theo thẩm quyền"]
    F --> H["Fix + retest + kiểm tra dữ liệu"]
    G --> H
    H --> I["Reassessment, residual risk, cập nhật controls"]
~~~

### 19.3. Tình huống không có log đầy đủ

Nếu một API export từng cho phép truy cập chéo lớp nhưng log lưu thiếu, không thể kết luận đã lộ dữ liệu hay chưa chỉ từ việc **không có record**. Cần:

- Xác minh phạm vi lỗ hổng và thời gian có thể xảy ra.
- Đánh giá độ đầy đủ, integrity của log, khả năng đối chiếu các nguồn khác.
- Kiểm tra file/job/response thực tế, bên nhận và downstream copies.
- Phân biệt **đã chứng minh lộ dữ liệu**, **chưa biết**, **không ghi nhận bằng chứng**.
- Dùng mức bất định làm đầu vào risk/incident decision.

Data owner hỗ trợ impact assessment; việc kết luận kỹ thuật và nghĩa vụ phải có các nhóm đúng thẩm quyền.

## 20. Data ownership assurance: chứng minh vai trò đang có hiệu quả

### 20.1. Từ tên owner đến assurance claim

Một claim có thể là:

> **Trong phạm vi data domains quan trọng thuộc nền tảng học và kỳ đánh giá xác định, mỗi domain có accountable owner được phê duyệt, đã xác định classification và các yêu cầu sử dụng/bảo vệ; các quyền và luồng chia sẻ quan trọng được kiểm tra theo các tiêu chí đã duyệt, các ngoại lệ và phát hiện chưa khắc phục được ghi rõ.**

Không nên viết “mọi dữ liệu của tổ chức đều bảo mật hoàn toàn”. Claim tốt phải ghi **scope, thời kỳ, control và điểm chưa được bao phủ**.

### 20.2. Claim–Argument–Evidence

**Claim:** Data domain “kết quả học tập” được quản trị và bảo vệ theo yêu cầu đã phê duyệt trong phạm vi API, database, worker và export storage production.

**Argument:**

1. Domain, tài sản, classification và mục đích được data owner xác định.
2. Data flows và bản sao thuộc scope được inventory và liên kết owner.
3. Yêu cầu truy cập/xuất/sửa/giữ dữ liệu có tiêu chí test cụ thể.
4. Engineering/Platform thực thi authorization, storage protections, logging, backup và những controls đã chọn.
5. Security/QA đánh giá hành vi và evidence theo design, implementation, operating effectiveness.
6. Findings và residual risk được theo dõi/giải quyết theo thẩm quyền.
7. Trigger thay đổi làm phát sinh reassessment khi mục đích, data flow hoặc quyền khác trước.

**Evidence:**

- Data ownership register có phiên bản và phê duyệt.
- Data classification và data dictionary, lineage/data flow.
- Security requirements, threat model, use/abuse cases.
- IAM/data access review, approval records và các quyền thực tế.
- API negative tests, export job/file tests, runtime config.
- ETL/data quality checks, restore tests khi liên quan.
- Vendor data-sharing record, contract/retention controls.
- Audit log health, incident/finding/retest history.
- Assessment report có scope, kỳ, giới hạn và người review.

### 20.3. Ba lớp kiểm chứng

| Lớp | Câu hỏi | Evidence ví dụ | Không thể suy ra |
|---|---|---|---|
| **Design effectiveness** | Data owner đã đặt mục tiêu, classification và control phù hợp risk chưa? | Risk assessment, policy, data flow, approval | Chưa chứng minh đã triển khai đúng |
| **Implementation effectiveness** | Rules và controls có thật ở những đường trong scope? | IAM/config, code, schema, test trong môi trường xác định | Chưa chứng minh ổn định suốt kỳ |
| **Operating effectiveness** | Ownership, approval, access review, retention và monitoring có hoạt động đúng trong kỳ? | Access review records, log, sampled changes, deletion/recovery tests | Không chứng minh phần ngoài scope hoặc log thiếu |

Một lần ký phê duyệt data policy thuộc evidence về quản trị/thiết kế; **không thay thế** kiểm tra dữ liệu production có được truy cập đúng hoặc đã được xóa đúng hạn hay không.

### 20.4. Chuỗi truy vết

~~~mermaid
flowchart TD
    A["Data domain + accountable owner"] --> B["Purpose, classification, obligations"]
    B --> C["Risk scenarios và data requirements"]
    C --> D["Controls + technical owners"]
    D --> E["Test/evidence: API, storage, access, retention"]
    E --> F{"Đạt theo scope và kỳ?"}
    F -->|"Có"| G["Assurance claim có giới hạn"]
    F -->|"Không đạt"| H["Finding → remediation → retest"]
    F -->|"Thiếu evidence"| I["Evidence request / scope gap"]
    H --> D
    I --> E
    G --> J["Residual risk / quyết định đúng thẩm quyền"]
    J --> K["Monitoring + reassessment triggers"]
    K --> B
~~~

## 21. Evidence standard và phép kiểm thử cho data owner controls

### 21.1. Những thuộc tính evidence cần thiết

| Tiêu chí | Câu hỏi | Ví dụ chưa đủ |
|---|---|---|
| **Relevance** | Evidence chứng minh đúng policy và claim về dữ liệu? | Policy encryption để chứng minh authorization theo lớp |
| **Completeness** | Đã bao phủ các dataset, bản sao, downstream, tenant? | Chỉ xem operational DB, bỏ data lake |
| **Scope** | Dữ liệu, môi trường và actor nào được xét? | Test ở staging nhưng claim production |
| **Freshness/period** | Dữ liệu và quyết định còn hiệu lực trong kỳ? | Classifications cũ trước khi thêm PII |
| **Provenance** | Ai tạo, từ nguồn nào, tool và query nào? | File export không biết nguồn |
| **Integrity** | Có thể kiểm tra thay đổi trái phép? | Bảng review bị sửa không có lịch sử |
| **Reliability** | Nguồn và hệ thống thu thập có đáng tin? | Scanner bỏ sót bucket không được tag |
| **Representativeness** | Sample hợp lệ cho kết luận? | Chỉ chọn vài request thành công |
| **Repeatability** | Người khác có thể đối chiếu và chạy lại? | Nhân viên nói “đã xem rồi” |
| **Confidentiality** | Evidence có làm lộ dữ liệu cần bảo vệ? | Đính kèm toàn bộ danh sách học viên vào ticket công khai |

### 21.2. Test matrix minh họa

| Test ID | Data owner requirement | Phép kiểm tra | Expected result | Evidence |
|---|---|---|---|---|
| DO-01 | Domain trọng yếu có owner | Đối chiếu catalog và danh sách domain thực | Không có domain trọng yếu vô chủ, ngoại lệ được giao xử lý | Catalog, approval, exception |
| DO-02 | Classification phản ánh dữ liệu | Chọn dataset theo rủi ro, kiểm tra schema/payload | Classification đúng và control phù hợp | Dictionary, payload đã kiểm soát |
| DO-03 | Người ngoài quyền không đọc điểm | Giảng viên lớp 42 yêu cầu dữ liệu lớp 43 | Deny, không side effect rò dữ liệu | API test, job/file trace |
| DO-04 | Bulk export chỉ gồm trường được duyệt | So sánh export schema và data contract | Không xuất trường ngoài scope | Payload/schema diff |
| DO-05 | Dữ liệu vendor trong scope hợp đồng | Review IAM/OAuth, kiểm thử API | Token không đọc data ngoài quyền | Token scope, negative test |
| DO-06 | Tài khoản nghỉ việc bị thu hồi | Đối chiếu leaver event và quyền thực tế | Quyền hết theo policy và SLA | IAM export, access test |
| DO-07 | Dữ liệu chính thức không bị sửa ngoài workflow | Thử cập nhật trái role/trạng thái | Deny và không sửa DB | Test, change/audit log |
| DO-08 | Dataset có thể khôi phục | Restore test với kiểm tra integrity | Đạt RPO/RTO và completeness đã phê duyệt | Restore report, comparison |
| DO-09 | Dữ liệu hết retention được xử lý | Chọn mẫu và kiểm tra xóa/giữ hợp lệ | Không còn dữ liệu trái chính sách; exception rõ | Deletion, backup/vendor evidence |
| DO-10 | Data flow mới được review | Kiểm tra release có thêm webhook | Có approval và controls trước khi chuyển dữ liệu | PR, assessment, runtime test |
| DO-11 | Data owner thay đổi được bàn giao | Kiểm tra chuyển ownership | Owner mới nhận các open findings/approvals | Change record, review |
| DO-12 | Telemetry dữ liệu nhạy cảm còn hoạt động | Synthetic event không chứa PII thật | Log/alert đi đúng tuyến và owner | Event, SIEM rule/ticket |
| DO-13 | Dữ liệu phái sinh giữ giới hạn mục đích | Review lineage/data product | Phần dẫn xuất có owner, scope và policy | Data contract, lineage |
| DO-14 | Kết thúc vendor không còn luồng dữ liệu | Revoke token và dừng scheduled job | Không còn export mới, dữ liệu cũ theo thỏa thuận | Revoke test, job logs, vendor record |

Không thể kết luận pass chỉ vì có test ID. Cần **bộ dữ liệu, thời điểm, kết quả thực, build/config, phạm vi, reviewer và limitations**.

### 21.3. Phân loại kết luận

- **Pass / supported:** control đạt tiêu chí trong scope/kỳ và evidence đủ.
- **Fail / unsupported:** có sai lệch được xác minh, phải ghi finding.
- **Insufficient evidence:** thiếu nguồn, coverage, test hoặc dữ liệu không đáng tin; không được xem như pass.
- **Not applicable:** requirement không liên quan tới scope có căn cứ và review trigger.
- **Exception/accepted residual risk:** quyết định quản trị riêng, **không biến test fail thành pass**.

Khi framework audit cụ thể dùng các trạng thái khác, tổ chức phải tuân thủ quy tắc của chương trình đó, không áp một bảng từ vựng tùy ý.

## 22. Mẫu data ownership register có liên kết assurance

Dưới đây là **YAML minh họa** cho một domain, không phản ánh dữ liệu thật hay bằng chứng đã được kiểm chứng.

~~~yaml
domain_id: DATA-ACADEMIC-RESULTS
name: "Kết quả học tập"
description: "Điểm, trạng thái bài nộp và kết quả học vụ"
accountable_data_owner:
  role: "Academic Business Owner"
  approval_reference: "Internal governance decision - placeholder"
backup_owner:
  role: "Academic Operations Manager"
data_steward:
  role: "Academic Data Steward"
custodians:
  - "Learning Backend Team"
  - "Database and Cloud Operations"
system_owners:
  - "Learning Platform Service Owner"
classification:
  level: "Confidential - scheme minh họa"
  privacy_flags: ["Check applicable personal-data obligations"]
scope:
  environments: ["production"]
  source_of_truth: "Academic records domain"
  systems:
    - "learning-api"
    - "academic-database"
    - "export-worker"
    - "private-export-storage"
  excluded:
    - "Historical partner systems pending inventory"
purposes:
  approved:
    - "Teaching, marking and learner progress reporting"
  new_uses_require_review: true
access_rules:
  - requirement_id: "DO-AC-01"
    objective: "Only authorized actor can access class records"
  - requirement_id: "DO-AC-02"
    objective: "Export includes only approved fields and classes"
  - requirement_id: "DO-INT-01"
    objective: "Official grades have authorized change history"
retention:
  rule_reference: "Approved academic retention schedule - placeholder"
  backup_and_vendor_rules: "Must be assessed separately"
shared_responsibilities:
  business_policy: "Accountable data owner"
  technical_controls: "Backend, Platform and Data Engineering"
  independent_assurance: "Security Assurance Reviewer"
risk_scenarios:
  - "Cross-class data disclosure"
  - "Unauthorized grade modification"
  - "Excessive vendor analytics export"
control_ids:
  - "CTRL-APP-AUTHZ-01"
  - "CTRL-DATA-EXPORT-01"
  - "CTRL-DATA-INTEGRITY-01"
evidence_requirements:
  - "Versioned authorization tests and job/file side effects"
  - "Access review with effective permissions"
  - "Data classification and lineage review"
  - "Retention/deletion and restore evidence as applicable"
assessment:
  period: "Define actual review period"
  result: "Pending verification"
  limitations:
    - "No claim for uninventoried historical partner systems"
  open_findings: []
review:
  trigger_events:
    - "New data purpose or recipient"
    - "New dataset, tenant, export or provider"
    - "Incident, critical finding or owner change"
  next_review: "Schedule according to risk-based policy"
~~~

**Lưu ý:** Không sử dụng các giá trị placeholder như một hồ sơ phê duyệt thật. Domain ownership phải liên kết các ID thực tế của hệ thống GRC, data catalog, control register và evidence repository. Nếu hệ thống lưu cả dữ liệu chưa inventoried, phải ghi **scope gap**, không tự loại trừ để có kết luận “đạt toàn bộ”.

## 23. Case study: chủ sở hữu dữ liệu học viên và đường export Java

### 23.1. Bối cảnh

Một nền tảng học trực tuyến có:

- **Academic Data Owner**: chịu trách nhiệm kết quả học tập.
- **Learning Backend Team**: vận hành Java API và authorization.
- **Data/DB Team**: quản lý database, backup và tính toàn vẹn pipeline.
- **Platform Team**: quản lý queue/worker, IAM và private object storage.
- **Analytics Team**: dùng dataset tổng hợp được duyệt.
- **Security Assurance/Privacy**: xác định kiểm tra và nghĩa vụ.
- **Vendor SaaS**: nhận một tập chỉ số đã được chấp thuận.

Data owner quy định:

> Giảng viên chỉ xuất bảng điểm của lớp đang được phân công; file chỉ chứa những trường phục vụ giảng dạy; mọi hoạt động xuất nhạy cảm phải có dấu vết; dữ liệu chia sẻ cho Analytics/Vendor chỉ ở phạm vi được duyệt.

Đây là **quy tắc nghiệp vụ được phê duyệt**. Để biến thành control cần chủ thể, đối tượng, điểm thực thi và bằng chứng.

### 23.2. Mô hình threat/risk

| Risk | Điều kiện và hậu quả | Control owner |
|---|---|---|
| R-DATA-01 | Giảng viên nhập classId của lớp khác, xuất trái phép dữ liệu | Backend/Authorization |
| R-DATA-02 | Job payload có scope bị thay, worker đọc toàn DB | Backend + Worker |
| R-DATA-03 | Signed URL có thể bị dùng lại ngoài quyền | Platform/Storage |
| R-DATA-04 | Export chứa thêm email, ghi chú hoặc dữ liệu không cần thiết | Backend/Data |
| R-DATA-05 | Vendor được cấp OAuth token quá rộng | IAM/Integration |
| R-DATA-06 | Data quality/ETL sai làm báo cáo điểm không đúng | Data Engineering |
| R-DATA-07 | Không có log để điều tra export bất thường | SecOps/Platform |
| R-DATA-08 | Ownership không được cập nhật khi đổi Academic Head | Data Governance |
| R-DATA-09 | File export và bản sao vendor giữ vượt thời hạn | Custodian/Vendor owner |

Các risk scenarios là **giả thuyết phân tích**, không phải khẳng định hệ thống thật có lỗi.

### 23.3. Phác thảo policy authorization bằng Java

Đoạn mã sau minh họa cách **technical control thực thi chính sách do data owner đưa ra**, không phải hàm tạo file hoàn chỉnh:

~~~java
public ExportRequestId requestGradesExport(
        AuthenticatedPrincipal actor,
        long classId) {

    // Quyền được quyết định từ danh tính đã xác thực
    // và quan hệ lớp tại nguồn được tổ chức tin cậy.
    if (!gradeAccessPolicy.canExportGrades(actor.userId(), classId)) {
        throw new AccessDeniedException("Export not permitted");
    }

    // Schema được xác định phía server theo data contract,
    // không lấy danh sách cột tùy ý từ client.
    var fields = approvedExportSchema.forClassGrades();

    // Scope actor, class và fields phải được ràng buộc
    // trong job; worker/download vẫn cần kiểm soát.
    return gradesExportService.scheduleAuthorizedExport(
            actor.userId(), classId, fields);
}
~~~

Mã minh họa mới kiểm tra quyết định tại **đường tạo request**. Nó **không chứng minh** worker bảo toàn scope, quyền tải file, trạng thái quyền bị thu hồi, data classification, tính an toàn của storage hoặc việc field list thật sự có đúng runtime schema. Cần kiểm tra các phần đó riêng.

### 23.4. Test e2e cần có

1. Giảng viên A có quyền lớp 42 → export đúng tập dữ liệu lớp 42, schema chỉ có trường được duyệt.
2. A yêu cầu lớp 43 không có quyền → bị từ chối; **không có job/file/DB side effect** ngoài quyền.
3. A có quyền lớp 42 nhưng thử yêu cầu thêm trường hạn chế → backend bỏ hoặc từ chối theo data contract.
4. Quyền của A bị thu hồi giữa lúc tạo job và lúc tải → hành vi theo **revocation policy đã công bố**, có test và giới hạn rõ.
5. Một job payload sai scope → worker không xử lý dữ liệu ngoài phạm vi, có log và thông tin xử lý.
6. Actor không có quyền với file → không tải được qua đường được bảo vệ, kiểm tra signed URL/ACL theo thiết kế.
7. Token của Analytics/Vendor không thể đọc raw grades ngoài scope được duyệt.
8. Log ghi đầy đủ actor, action, dataset, thời điểm, kết quả và correlation ID cần thiết mà không lưu toàn bộ dữ liệu điểm hoặc secret.
9. Khi export bị lỗi giữa chừng, file tạm không công khai và được cleanup phù hợp.
10. Khi có release mới, test evidence liên kết đúng **build/artifact/deploy**.

Data owner quyết định **đúng đối tượng/trường/mục đích**, không cần trực tiếp viết test Java. Backend/QA phát triển test; Security Assurance đánh giá evidence; risk owner xử lý residual risk vượt ngưỡng.

### 23.5. Kết luận không nên rộng hơn kiểm thử

Giả sử những test trên pass trong staging nhưng production có thêm một batch export legacy không nằm trong inventory. Báo cáo phù hợp:

> Các đường export đã kiểm thử đáp ứng tiêu chí trong phiên bản và môi trường được ghi. **Chưa đủ bằng chứng** cho batch export legacy và phần cấu hình production chưa đối chiếu. Cần xác minh những đường này trước khi đưa ra claim cho toàn bộ production.

Không nên tuyên bố “data owner đã xác nhận nên mọi export an toàn”. **Owner approval và assurance conclusion là hai bước khác nhau**.

## 24. Handling finding, exception và residual risk

### 24.1. Phân biệt ba loại vấn đề

| Tình trạng | Ví dụ | Hành động |
|---|---|---|
| **Control failure** | API xuất dữ liệu lớp ngoài quyền | Containment, risk analysis, fix và retest |
| **Evidence gap** | Không có log hoặc inventory của một bucket legacy | Tìm nguồn, giới hạn claim, bổ sung kiểm tra |
| **Governance ownership gap** | Dataset critical không có data owner rõ | Chỉ định owner, kiểm tra access/purpose/retention |
| **Policy exception** | Cần chia sẻ tạm dataset ngoài baseline đã duyệt | Review điều kiện/risks, phê duyệt đúng thẩm quyền, giới hạn |
| **Accepted residual risk** | Control bù trừ vẫn để lại tác động được nhận diện | Record có scope, time limit, monitoring và risk owner |

Một data owner có thể là người phát hiện, đề xuất khắc phục hoặc phê duyệt **trong quyền được giao**. Không tự suy ra data owner được phép chấp nhận rủi ro vượt appetite hoặc miễn các yêu cầu bắt buộc.

### 24.2. Ví dụ finding: export thiếu điều kiện tenant

**Quan sát:** test gửi một classId hợp lệ thuộc tenant B từ tài khoản giảng viên tenant A; endpoint trả dữ liệu học viên tenant B.

**Bằng chứng:** test fixture, response được che dữ liệu nhạy cảm, access decision, DB query/worker trace, build/deployment, thời gian thực hiện.

**Tác động:** lộ dữ liệu ngoài tenant. Cần điều tra việc dữ liệu thật có bị truy cập trước đó không, không tự khẳng định có hoặc không có breach.

**Khắc phục:** thêm tenant boundary check tại nguồn đáng tin, sửa query và worker/file paths, bổ sung regression test, review những tuyến tương tự và retest production theo quy trình.

**Data owner:** xác định dataset/tác động nghiệp vụ, ưu tiên, phạm vi thông tin bị ảnh hưởng và điều kiện tái mở chức năng, phối hợp với Security/Privacy/IR.

**Assurance reviewer:** chỉ kết luận sau khi xem evidence, nêu scope và limitations. Pull request merged không tự chứng minh control production đã đạt.

### 24.3. Ngoại lệ có thời hạn

Một dự án migration cần chia sẻ một dataset restricted sang môi trường tạm. Có thể xem xét ngoại lệ nội bộ nếu chính sách cho phép và nghĩa vụ không cấm, nhưng record phải có:

- Dataset, mục đích, người nhận, môi trường và thời gian.
- Rủi ro và lý do không dùng cách an toàn thông thường.
- Đánh giá Privacy/Legal khi áp dụng.
- Control bù trừ được **triển khai và kiểm chứng**.
- Approval đúng thẩm quyền và owner theo dõi.
- Ngày hết hiệu lực, trigger chấm dứt, kế hoạch xóa/thu hồi.
- Test, log, bằng chứng xử lý và residual risk.

**Không có ngoại lệ nào tự biến control fail thành Pass.** Một exception có thể cho phép tiếp tục công việc trong điều kiện xác định nhưng sai lệch vẫn phải được ghi trung thực.

## 25. Continuous data ownership assurance

### 25.1. Khi nào phải đánh giá lại?

Những trigger quan trọng:

- Thêm loại dữ liệu, trường nhạy cảm hoặc nhóm người dùng.
- Đưa dữ liệu vào data lake, analytics, AI/ML hoặc vendor mới.
- Thay classification hoặc mục đích xử lý.
- Giao owner mới, đổi tổ chức hoặc phát hiện dataset mồ côi.
- Mở API/bulk export, share link hoặc thay cơ chế authorization.
- Đổi nơi lưu, region, backup, retention hoặc cách xóa.
- Có incident, quyền vượt phạm vi, sai dữ liệu hoặc failed restore test.
- Đổi điều khoản hợp đồng hoặc nghĩa vụ pháp lý áp dụng.
- Có finding, ngoại lệ hết hạn hoặc một control không còn hoạt động.

### 25.2. Giám sát theo vòng đời

| Giai đoạn | Trách nhiệm data owner | Evidence/đầu ra |
|---|---|---|
| Data discovery | Xác nhận domain, owner, source và use cases | Inventory, catalog, classification |
| Design | Thống nhất mục đích, rủi ro và requirements | Data flow, risk treatment, data contract |
| Development | Review thay đổi ảnh hưởng data use/protection | PR/change, schema review, security tests |
| Release | Chấp thuận phạm vi yêu cầu mới theo risk | Decision record, deploy/test mapping |
| Operations | Review access, quality, retention, data sharing | Access diff, quality dashboards, deletion evidence |
| Incidents | Hỗ trợ scope/impact và biện pháp ưu tiên | Incident record, affected dataset map |
| Audit/assurance | Xác nhận tiêu chí và giải thích evidence gaps | Evidence catalog, assessment |
| Decommission | Xác nhận cần giữ/trả/xóa dữ liệu nào | Exit plan, revoke/deletion/retention records |

Data owner không phải thực hiện mọi thao tác. **Một chương trình hiệu quả phân biệt người accountable và người thực thi control**, rồi thiết lập nhịp review đủ bền vững với thay đổi.

### 25.3. Nguồn tín hiệu tự động

Một số nguồn có thể hỗ trợ:

- Data discovery/catalog scanner phát hiện dataset hoặc schema mới.
- Cloud/IAM policy diff và access analytics.
- DLP events hoặc cảnh báo data egress trong phạm vi được phê duyệt.
- CI/CD schema/payload tests, contract tests và export authorization tests.
- ETL lineage, data quality rule failures.
- Retention/deletion job results và kho yêu cầu xóa.
- Backup/restore test summaries.
- Supplier change notifications và incident reports.
- Data access review approvals và remediation tickets.

Automation không thay data owner quyết định **mục đích và mức impact nghiệp vụ**. Bản thân pipeline evidence cũng cần kiểm tra completeness, scope, provenance và tính hoạt động.

## 26. Metrics cho data ownership và assurance

| Metric | Mục đích | Giới hạn |
|---|---|---|
| % critical data domains có accountable owner và người thay | Độ rõ accountability | Tên owner không chứng minh đang review |
| % datasets có classification và source of truth | Độ phủ inventory | Scanner có thể bỏ shadow datasets |
| % shared datasets có approved purpose/recipient | Kiểm soát chia sẻ | Có approval không chứng minh payload đúng |
| % data controls critical có evidence hợp lệ | Mức bao phủ security assurance | Evidence cũ/sai kỳ có thể bị tính nhầm |
| % access reviews hoàn thành và revoke được xác minh | Hiệu quả kiểm soát quyền | Tích chọn “review done” không chứng minh effective access đã đổi |
| % retention/deletion jobs được kiểm tra chất lượng | Kiểm soát vòng đời | Job success không bao phủ backup/vendor |
| Số orphan datasets phát hiện/giải quyết | Giảm khoảng trống ownership | Ít orphan có thể do discovery yếu |
| Số finding data protection quá hạn theo mức risk | Rủi ro tồn đọng | Đóng ticket chưa retest làm lệch số |
| Tỷ lệ data-sharing changes được review trước release | Giảm rủi ro mục đích mới | Change không qua workflow có thể bị bỏ sót |
| Số vendor scopes vượt mục đích đã phê duyệt | Khả năng phát hiện chia sẻ quá rộng | Scope chỉ nói quyền tiềm năng, cần kiểm tra sử dụng |
| Restore success theo dataset và mục tiêu RPO/RTO | Độ sẵn sàng dữ liệu | Diễn tập có thể chưa thử kịch bản nghiêm trọng |
| % remediation có retest đúng môi trường | Chất lượng khắc phục | Test pass ở staging không tự bao phủ production |
| % owner changes có bàn giao findings/permissions | Quản trị thay người | Có biên bản không chứng minh findings đã xử lý |

### 26.1. Tránh chỉ số “100% compliant” không có căn cứ

Nếu dashboard báo 100% datasets đã có owner, cần hỏi:

1. **Mẫu số** bao gồm những nơi lưu nào, data lake, backup, vendor và dataset dẫn xuất?
2. Owner được chỉ định nhưng **còn tại nhiệm và có quyền quyết định không**?
3. Classification, mục đích và retention đã được review chưa?
4. Có những dataset ngoài inventory bị bỏ qua?
5. Có phân biệt **coverage của catalog** và **effectiveness của controls**?
6. Những finding/evidence gaps trọng yếu có được trình bày riêng?
7. Kỳ đánh giá và thay đổi gần đây có được phản ánh?

Một tỷ lệ đẹp không thay thế báo cáo **rủi ro và bất định có ý nghĩa**.

## 27. Những sai lầm thường gặp

**“Ai quản trị database thì người đó sở hữu dữ liệu.”** Không nhất thiết. Data custodian vận hành kỹ thuật, còn mục đích và tác động nghiệp vụ thuộc trách nhiệm được giao cho data owner.

**“Data owner được làm mọi thứ với dữ liệu.”** Sai. Quyết định nội bộ chịu giới hạn bởi pháp luật, hợp đồng, mục đích, chính sách và thẩm quyền.

**“Một dataset có hai owner thì cả hai tự phê duyệt được.”** Không nếu thiếu accountability cuối cùng và cơ chế xử lý xung đột.

**“Dữ liệu được ETL sang kho khác thì thuộc owner của hạ tầng mới.”** Không tự động. Lineage, mục đích, nghĩa vụ và quyết định bàn giao phải được ghi nhận.

**“Đã điền tên owner vào catalog nghĩa là bảo mật đạt.”** Chưa đủ. Cần requirements, controls, tests, evidence và operating review.

**“Chính sách yêu cầu mã hóa nên chỉ cần thấy encryption enabled.”** Chưa chứng minh quản lý khóa, quyền giải mã, dữ liệu trong truyền hoặc log/bản sao đã được bảo vệ phù hợp.

**“Vendor có chứng nhận nên có thể nhận dữ liệu ngoài mục đích.”** Không. Chứng nhận có phạm vi; bên sử dụng vẫn cần giới hạn dữ liệu và nghĩa vụ chia sẻ.

**“Dữ liệu hash ID đã là dữ liệu ẩn danh.”** Không mặc nhiên; có thể cần đánh giá khả năng liên kết/tái nhận dạng.

**“Data owner phê duyệt truy cập đồng nghĩa server tự biết kiểm tra quyền.”** Approval phải được chuyển thành control ở đúng PEP; API, worker, file và tenant boundaries phải được test.

**“Có backup thành công là dữ liệu đã phục hồi được.”** Cần restore test, integrity và thời gian so với mục tiêu.

**“Tài khoản đã xóa nghĩa mọi bản sao dữ liệu cũng đã xóa.”** Cần xem cache, warehouse, vendor, backup, log và retention exceptions.

**“Không có incident là bằng chứng data protection đạt.”** Thiếu telemetry hoặc khả năng phát hiện có thể che sai lệch.

**“Không có evidence nghĩa là control chắc chắn fail.”** Thiếu bằng chứng là một trạng thái riêng nhưng cũng không thể báo Pass.

**“Risk owner đã ký chấp nhận thì khỏi ghi finding.”** Acceptance không sửa sự thật kỹ thuật hoặc xóa nghĩa vụ bắt buộc.

**“Dữ liệu chỉ cần owner khi tạo mới.”** Owner, purposes, recipients và rủi ro thay đổi liên tục, cần review theo trigger.

## 28. Bài tập thực hành

### Bài tập A — Phân biệt owner và custodian

Một trường đại học dùng cloud database cho hồ sơ học viên. DBA giữ toàn bộ quyền truy cập, Product Manager muốn chia sẻ điểm cho đối tác tuyển dụng và phòng đào tạo muốn giữ toàn bộ dữ liệu không giới hạn.

Hãy xác định:

1. Data domain và owner nghiệp vụ hợp lý theo phân quyền tổ chức.
2. Custodian, system owner, Privacy/Legal và risk owner.
3. Ai được phê duyệt mục đích, ai thực thi database permissions?
4. Những điều kiện nào phải được kiểm tra trước khi chia sẻ cho đối tác?
5. Evidence nào chứng minh chỉ đúng dữ liệu được chia sẻ?
6. Nếu có bất đồng về retention, ai xử lý và theo quy trình nào?

**Gợi ý:** Người có quyền SQL không đương nhiên quyết định phạm vi công bố; tên data owner không thay căn cứ pháp lý hoặc thỏa thuận cần thiết.

### Bài tập B — Xây data ownership catalog

Nền tảng có các datasets: hồ sơ học viên, bài nộp, kết quả học tập, email notification logs, analytics event stream và dữ liệu báo cáo tổng hợp.

Tạo một bảng cho mỗi dataset:

- Domain ID/description, accountable owner, steward, custodian.
- Classification và mục đích hợp lệ.
- Source of truth, consumers, downstream copies.
- Access requirements, retention/archival rules và trigger review.
- Risk scenario trọng yếu.
- Kiểm thử và evidence dùng để kết luận control đạt.

**Gợi ý:** Email logs có thể chứa PII; báo cáo tổng hợp có thể vẫn tiết lộ nhóm nhỏ. Không mặc định mọi dữ liệu “analytics” là public.

### Bài tập C — Dữ liệu phái sinh và AI

Đội Analytics muốn dùng bài luận của học viên để tạo mô hình dự đoán nguy cơ bỏ học. Nhóm phát triển cho rằng “tài liệu đã được lưu trong cloud của công ty nên dùng được”.

Hãy phân tích:

1. Mục đích mới khác mục đích thu thập ban đầu ở đâu?
2. Dữ liệu gốc, đặc trưng, model artifacts và output cần owner nào?
3. Quy tắc chia sẻ, giới hạn trường và retention nên xác định ra sao?
4. Những nghĩa vụ privacy/pháp lý nào cần được đánh giá bởi chuyên trách?
5. Data flow và các rủi ro tái nhận dạng, data leakage, integrity?
6. Evidence nào chứng minh phương án dùng dữ liệu phù hợp với quyết định?

**Gợi ý:** Không phê duyệt chỉ vì dataset ở trong tài khoản cloud của tổ chức. Dữ liệu suy luận có thể nhạy cảm ngay cả khi bỏ tên người học.

### Bài tập D — Authorization theo quyết định data owner

Data owner của kết quả học tập quy định mỗi giảng viên chỉ được xuất dữ liệu lớp đang phụ trách. Java API có role check TEACHER nhưng không kiểm tra classId; worker tạo file vào object storage.

Hãy thiết kế:

- Security invariant và ít nhất ba requirements có thể kiểm thử.
- Positive test cho lớp được phân công.
- Negative test cho lớp khác và tenant khác.
- Side-effect tests cho queue/file/storage.
- Evidence gắn build, deployment, IAM và policy version.
- Điều kiện đóng finding sau sửa.
- Báo cáo claim có scope/kỳ và limitations.

**Gợi ý:** Một HTTP 403 không đủ nếu worker vẫn xuất file; data owner cung cấp quyết định về quyền, engineering triển khai và assessor kiểm tra.

### Bài tập E — Retention và deletion

Một công cụ hỗ trợ học viên lưu email, ticket, ghi chú và bản sao danh sách học viên. Hợp đồng với vendor hết hạn; Product đã xóa dữ liệu tại ứng dụng chính nhưng sao lưu vẫn còn và scheduled export job vẫn chạy.

Hãy lập quy trình:

1. Định nghĩa những datasets/bản sao thuộc scope.
2. Phân biệt ngừng truy cập, ngừng truyền dữ liệu và xóa/giữ dữ liệu.
3. Xác định Legal/Privacy và hợp đồng cần rà soát.
4. Revoke credential và ngắt job trong các hệ thống liên quan.
5. Thu thập evidence từ storage, backups và vendor.
6. Ghi điều chưa thể xác minh thay vì tuyên bố đã xóa toàn bộ.
7. Cập nhật catalog, risk register và review trigger.

### Bài tập F — Assurance với evidence gap

Một cuộc review có dữ liệu sau:

- 20 critical datasets được ghi trong catalog; 18 có owner hiện hành.
- 16 có classification được review trong kỳ; 4 chưa được cập nhật.
- Tất cả có encryption-at-rest config trong một cloud account.
- Chỉ 12 đã có negative access tests tương ứng.
- Có 2 dataset ở vendor chưa có data-flow map.
- Một file export được chứng minh tải được bởi actor ngoài quyền.

Hãy lập báo cáo:

1. Claim nào được hỗ trợ và claim nào chưa được chứng minh?
2. Vấn đề nào là control failure, evidence gap và ownership gap?
3. Những rủi ro nào cần xử lý trước, vì sao?
4. Data owner, custodian, Security, Privacy và risk owner làm gì?
5. Phép thử/retest và evidence bổ sung cần có?
6. Có được viết “100% dữ liệu được bảo vệ” không?

**Gợi ý:** Hai dataset vô chủ và các đường chưa test cần remediation/investigation. File tải ngoài quyền là **control failure được chứng minh**. Một cloud encryption screenshot không chứng minh mọi hệ thống, luồng và quyền truy cập.

## 29. Checklist triển khai data ownership có bằng chứng

Dùng checklist để rà soát độ hoàn chỉnh; **đánh dấu đủ ô không phải chứng nhận rằng hệ thống đã an toàn**.

- [ ] Có data domains/datasets quan trọng, mục đích và nguồn dữ liệu rõ.
- [ ] Mỗi quyết định trọng yếu có một accountable owner và cơ chế thay thế/escalation.
- [ ] Phân biệt data owner, steward, custodian, system owner, risk owner và vai trò pháp lý.
- [ ] Có owner register/catalog, phiên bản và lịch cập nhật.
- [ ] Có classification scheme phù hợp tác động và nghĩa vụ áp dụng.
- [ ] Có data dictionary, source of truth và lineage cho luồng quan trọng.
- [ ] Có review đối với bản phái sinh, analytics, AI/ML và dữ liệu tổng hợp.
- [ ] Purpose, consumers và recipients được phê duyệt theo scope.
- [ ] Chính sách quyền được chuyển thành control thực tế ở API/worker/storage.
- [ ] Có kiểm tra object/tenant/field-level authorization, bulk export và side effects.
- [ ] Data owner tham gia xác định integrity rules, quality expectations và impact.
- [ ] Có mục tiêu availability, backup/restore phù hợp impact của dataset.
- [ ] Retention, archival, deletion, backup và vendor copies có owner và trách nhiệm.
- [ ] Data sharing/vendor agreements và shared responsibility đã được xem theo nghĩa vụ.
- [ ] Có trigger review khi thay mục đích, schema, dữ liệu nhạy cảm, vendor, owner hoặc incident.
- [ ] Có design, implementation và operating evidence theo risk.
- [ ] Evidence có provenance, scope, period, integrity, completeness và limitations.
- [ ] Có test matrix và build/deploy mapping cho control ứng dụng.
- [ ] Ghi rõ Pass, Fail, Insufficient evidence, N/A và ngoại lệ có thẩm quyền.
- [ ] Finding có impact, owner, containment, remediation và retest.
- [ ] Risk acceptance không che đi control failure hoặc nghĩa vụ bắt buộc.
- [ ] Có monitoring/detection và incident phối hợp đúng vai trò.
- [ ] Có đo độ phủ owner, access review, data sharing, retention và evidence gaps.
- [ ] Kết luận assurance nói rõ **điều gì được chứng minh** và **điều gì chưa được kiểm tra**.

## 30. Ghi nhớ

- **Chủ sở hữu dữ liệu là vai trò accountable đối với dữ liệu trong tổ chức**, không tự động là người có quyền sở hữu pháp lý tuyệt đối hoặc người quản trị database.
- Data owner xác lập **mục đích, phạm vi, phân loại, yêu cầu bảo vệ, tiêu chí chia sẻ và vòng đời** trong thẩm quyền; steward và custodian hỗ trợ hoặc thực thi.
- **Quyền phê duyệt nghiệp vụ không thay kiểm soát kỹ thuật**: authorization, least privilege, encryption, log, backup, retention và kiểm thử vẫn phải hoạt động ở các ranh giới thực.
- **Data ownership phải theo dữ liệu và lineage**, kể cả bản sao, dữ liệu phái sinh, báo cáo, AI/ML, hệ thống vendor và backup; đổi storage không tự chuyển accountability.
- **Dữ liệu cá nhân có nghĩa vụ riêng theo pháp luật áp dụng**; data owner nội bộ không đồng nhất với controller/processor hoặc DPO.
- Assurance cần bằng chứng phù hợp về **design, implementation và operating effectiveness**, có nguồn, kỳ, phạm vi, độ phủ và giới hạn.
- **Ownership gap, control failure và evidence gap khác nhau**; tất cả đều cần xử lý trung thực theo risk và không được tự báo Pass.
- Data owner và risk owner có thể là một hoặc nhiều người, nhưng **quyết định residual risk phải đúng ủy quyền**, không xóa findings hoặc nghĩa vụ bắt buộc.
- Chương trình trưởng thành duy trì vòng lặp **data domain + owner → risk → requirements → controls → test/evidence → assurance decision → remediation → monitoring/reassessment**.



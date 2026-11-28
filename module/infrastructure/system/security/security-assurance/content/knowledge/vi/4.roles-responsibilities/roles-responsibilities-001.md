# CISO

Trong chương **Vai trò và trách nhiệm**, **CISO (Chief Information Security Officer)** là người lãnh đạo chức năng bảo mật thông tin ở cấp tổ chức, chịu trách nhiệm định hướng chiến lược, quản trị chương trình bảo mật và báo cáo một cách có cơ sở về rủi ro, tình trạng kiểm soát và năng lực ứng phó. CISO giúp lãnh đạo hiểu: **tài sản nào cần bảo vệ, rủi ro nào đáng ưu tiên, tổ chức đang làm gì để kiểm soát và bằng chứng nào cho thấy các biện pháp thực sự có hiệu quả**.

Trong module **SECURITY_SECURITY_ASSURANCE**, CISO có vai trò then chốt khi xây dựng cách đánh giá có bằng chứng rằng hệ thống đạt mục tiêu bảo mật: thống nhất mục tiêu và mức rủi ro, điều phối thiết kế security controls, yêu cầu kiểm thử và audit, chỉ đạo khắc phục phát hiện, đồng thời duy trì **security assurance liên tục** trong phát triển và vận hành. CISO không phải cá nhân tự thực hiện mọi biện pháp kỹ thuật và cũng không có quyền tự động chấp nhận mọi loại rủi ro thay cho chủ sở hữu nghiệp vụ.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Mô tả vai trò, phạm vi quyền hạn và trách nhiệm giải trình của CISO trong mô hình quản trị bảo mật.
2. Phân biệt trách nhiệm của CISO với CEO/ban lãnh đạo, CIO, CTO, trưởng nhóm kỹ thuật, chủ sở hữu rủi ro, bộ phận tuân thủ và kiểm toán nội bộ.
3. Giải thích cách CISO chuyển mục tiêu kinh doanh và phân tích rủi ro thành chiến lược, chính sách, security controls và tiêu chí assurance.
4. Thiết kế cơ chế ra quyết định, báo cáo và phân công trách nhiệm cho đánh giá rủi ro, kiểm thử, audit, ngoại lệ và remediation.
5. Xây dựng tập bằng chứng để CISO có thể báo cáo **mức độ bảo đảm hợp lý trong phạm vi được kiểm chứng**, thay vì chỉ báo cáo số lượng chính sách hoặc công cụ đã triển khai.
6. Phân tích tình huống thực tế khi mục tiêu bảo mật, chi phí, tiến độ sản phẩm và hoạt động vận hành xung đột.

## 2. CISO là ai?

**CISO** thường là chức danh lãnh đạo về an toàn thông tin/an ninh mạng (information security/cybersecurity). Tùy quy mô và cấu trúc, vị trí này có thể báo cáo cho CEO, CIO, COO, CRO hoặc trực tiếp trao đổi định kỳ với ban điều hành, hội đồng quản trị hay ủy ban rủi ro. Tên gọi và tuyến báo cáo cụ thể có thể khác nhau, nhưng vai trò phải có **đủ thẩm quyền, nguồn lực và kênh báo cáo để cảnh báo rủi ro nghiêm trọng**.

### 2.1. Ba loại trách nhiệm cần phân biệt

- **Lãnh đạo chương trình (program leadership):** đề xuất chiến lược, tiêu chuẩn, ngân sách, năng lực nhân sự, mức ưu tiên và cơ chế đánh giá.
- **Điều phối kiểm soát (control governance):** xác định yêu cầu và tiêu chí, phân công control owner, theo dõi kết quả vận hành, ngoại lệ và hành động khắc phục.
- **Tư vấn và báo cáo rủi ro (risk advice & reporting):** cung cấp phân tích cho người có thẩm quyền ra quyết định, nêu rõ lựa chọn, rủi ro còn lại và mức tin cậy của bằng chứng.

Trách nhiệm **chịu rủi ro kinh doanh cuối cùng** thuộc về cấp có thẩm quyền được tổ chức quy định, thường là chủ sở hữu hoạt động/tài sản hoặc lãnh đạo được ủy quyền; trách nhiệm giám sát tổng thể thuộc ban lãnh đạo/hội đồng quản trị theo cơ cấu áp dụng. CISO có thể được giao quyền phê duyệt một số ngoại lệ hoặc rủi ro trong giới hạn rõ ràng, **không mặc nhiên là người sở hữu và phê duyệt mọi rủi ro**.

Một chức danh CISO hiệu quả không thể chỉ dựa trên sự hiện diện của một tên vị trí trong sơ đồ tổ chức. Cần xác định rõ **mandate** (nhiệm vụ được giao), phạm vi hệ thống, quyền tiếp cận thông tin, quyền yêu cầu cải tiến, cơ chế leo thang và người có thẩm quyền quyết định khi tồn tại bất đồng.

### 2.2. CISO không phải “người duy nhất chịu trách nhiệm bảo mật”

Một sản phẩm có thể sử dụng IAM, WAF, SAST, SIEM và công cụ theo dõi cloud, nhưng tất cả đều cần những người vận hành, cấu hình và sửa lỗi cụ thể:

- Product owner xác định giá trị và mức ảnh hưởng đối với nghiệp vụ.
- Engineering owner chịu trách nhiệm sửa code/kiến trúc và triển khai đúng.
- Platform/operations owner chịu trách nhiệm cấu hình, giám sát, quyền truy cập và khôi phục.
- CISO và nhóm security đặt chuẩn, tư vấn, đánh giá và báo cáo tình trạng bảo mật.
- Risk owner quyết định cách xử lý hoặc chấp nhận rủi ro trong giới hạn được giao.
- Internal audit đánh giá độc lập về hiệu quả quản trị và kiểm soát theo nhiệm vụ kiểm toán của mình.

Vì vậy, một kết luận kiểu **“CISO đã ký xác nhận nên ứng dụng an toàn”** không đủ giá trị assurance nếu thiếu tiêu chí, phạm vi, thời điểm và bằng chứng kỹ thuật/hoạt động phù hợp.

## 3. Vị trí CISO trong quản trị tổ chức

### 3.1. Quan hệ với các vai trò lân cận

| Vai trò | Trọng tâm | Quan hệ với CISO |
|---|---|---|
| **Hội đồng quản trị/ban điều hành** | Định hướng, giám sát, mức chấp nhận rủi ro và cấp nguồn lực trong thẩm quyền | Nhận báo cáo rủi ro, quyết định ưu tiên và xử lý tình huống vượt thẩm quyền |
| **CEO/COO** | Kết quả kinh doanh và vận hành toàn tổ chức | Bảo đảm bảo mật gắn với chiến lược, năng lực thực thi và liên tục kinh doanh |
| **CIO** | Dịch vụ CNTT và quản trị công nghệ thông tin | Phối hợp xây tiêu chuẩn, IAM, tài sản, hạ tầng, nhà cung cấp và vận hành |
| **CTO/VP Engineering** | Kiến trúc và phát triển sản phẩm/nền tảng | Phối hợp secure design, SDLC, CI/CD, xử lý lỗ hổng và phát hành |
| **CRO/ERM hoặc risk owner** | Khung quản trị rủi ro doanh nghiệp, quyết định xử lý rủi ro trong phạm vi | Chuẩn hóa đánh giá rủi ro, theo dõi rủi ro còn lại và quyết định chấp nhận |
| **Legal/Compliance/DPO khi có** | Nghĩa vụ pháp lý, hợp đồng, quyền riêng tư và tuân thủ | Xác định yêu cầu áp dụng, phối hợp xử lý dữ liệu và báo cáo sự cố |
| **Security engineering/SOC/GRC** | Thiết kế, theo dõi, đánh giá và hỗ trợ xử lý security controls | Nhận mục tiêu/chỉ đạo, cung cấp evidence và finding |
| **Internal audit** | Đưa ra đánh giá độc lập theo kế hoạch kiểm toán | Có thể sử dụng evidence phù hợp; bảo vệ tính độc lập khi đưa ra kết luận |

**CIO** chủ yếu quản trị hoạt động CNTT và **CTO** thường chú trọng công nghệ sản phẩm; CISO tập trung vào các mục tiêu bảo mật và rủi ro xuyên suốt. Ranh giới có thể giao nhau; tổ chức phải tránh “khoảng trống trách nhiệm” khi một sự cố liên quan đồng thời cloud, code, dữ liệu, nhà cung cấp và tài khoản người dùng.

**DPO (Data Protection Officer)**, nếu được chỉ định hoặc luật áp dụng yêu cầu, có chức năng về bảo vệ dữ liệu cá nhân và các điều kiện độc lập/trách nhiệm riêng theo khung pháp lý liên quan. Không mặc định CISO kiêm DPO hoặc một vai trò thay thế hoàn toàn vai trò kia.

### 3.2. Cách tiếp cận “ba tuyến” trong quản trị

Mô hình ba tuyến (Three Lines Model) có thể giúp phân biệt thực thi, giám sát và bảo đảm độc lập:

1. **Tuyến thứ nhất – vận hành/nghiệp vụ:** quản lý rủi ro trong công việc hằng ngày và vận hành control; ví dụ team backend chịu trách nhiệm sửa lỗ hổng authorization.
2. **Tuyến thứ hai – hỗ trợ và giám sát rủi ro/tuân thủ:** ban hành phương pháp, hỗ trợ tiêu chuẩn, kiểm tra và thách thức kết quả; một phần chức năng CISO/GRC có thể đảm nhiệm tùy cấu trúc.
3. **Tuyến thứ ba – kiểm toán nội bộ độc lập:** đưa ra đánh giá độc lập về quản trị rủi ro và kiểm soát cho cấp quản trị thích hợp.

Đây là **mô hình phân định chức năng**, không phải sơ đồ cố định rằng mọi nhóm kỹ thuật luôn ở tuyến thứ nhất hoặc CISO luôn nằm hoàn toàn ở tuyến thứ hai. CISO có thể trực tiếp quản lý một số team vận hành security (ví dụ SOC). Khi đó, cần phân biệt **người tạo bằng chứng**, **người đánh giá bằng chứng** và **người đưa kết luận độc lập**, tránh tự kiểm toán công việc của chính mình.

~~~mermaid
flowchart TB
    B["Ban lãnh đạo / Hội đồng quản trị<br/>Định hướng, giám sát, mức rủi ro chấp nhận"]
    C["CISO<br/>Chiến lược, tiêu chí, điều phối assurance, báo cáo"]
    O["Chủ sở hữu nghiệp vụ / rủi ro<br/>Quyết định xử lý trong thẩm quyền"]
    E["Engineering / Platform / Operations<br/>Thiết kế và vận hành security controls"]
    G["GRC / Security assurance<br/>Đánh giá tiêu chí, bằng chứng, finding"]
    A["Internal audit<br/>Đánh giá độc lập"]
    B --> C
    B --> O
    C --> E
    C --> G
    O --> E
    E -->|"Control evidence và test result"| G
    G -->|"Phát hiện và mức tin cậy"| C
    C -->|"Báo cáo rủi ro, khuyến nghị"| B
    A -.->|"Ý kiến độc lập"| B
    E -.->|"Hồ sơ và đối chiếu"| A
    G -.->|"Phương pháp và hồ sơ"| A
~~~

Trong thực tế, tuyến báo cáo phải được phê duyệt bằng văn bản. CISO cần kênh **escalation** đủ nhanh khi phát hiện một rủi ro đáng kể không được owner xử lý hoặc khi điều kiện phát hành không còn đáp ứng.

## 4. Quyền hạn cần có để thực hiện trách nhiệm

Một CISO được kỳ vọng chịu trách nhiệm về mức độ minh bạch của rủi ro phải có điều kiện thực hiện công việc:

- **Quyền xây dựng và đề xuất chính sách:** mục tiêu bảo mật, tiêu chuẩn control tối thiểu, yêu cầu evidence và quy trình ngoại lệ.
- **Quyền yêu cầu thông tin:** truy cập báo cáo sự cố, danh mục tài sản, trạng thái control, kết quả kiểm thử và các thay đổi quan trọng trong phạm vi được phép.
- **Quyền đánh giá/thách thức:** yêu cầu giải trình các claim “đạt” nhưng thiếu bằng chứng; đề xuất retest hoặc đánh giá độc lập.
- **Quyền điều phối xử lý:** ưu tiên finding, phân công và theo dõi owner cùng các bộ phận kỹ thuật/nghiệp vụ.
- **Quyền khuyến nghị ngăn phát hành hoặc dừng hoạt động rủi ro cao:** thẩm quyền ra quyết định cuối cùng phải được quy định rõ theo chính sách và cơ chế ủy quyền.
- **Quyền báo cáo/escalate:** chuyển rủi ro trọng yếu hoặc xung đột lợi ích tới đúng cấp, không bị chặn bởi nhóm đang chịu áp lực tiến độ.
- **Nguồn lực thực thi:** ngân sách, đội ngũ, công cụ, thời gian đánh giá và quyền hỗ trợ từ các control owner.

Không phải tổ chức nào cũng cho CISO quyền **veto** mọi bản phát hành. Điều quan trọng là làm rõ ai quyết định, ai chịu rủi ro, điều kiện ngoại lệ nào được phép, ai ghi nhận và ai có quyền leo thang.

## 5. Các nhóm trách nhiệm chính của CISO

### 5.1. Định hướng chiến lược bảo mật

CISO chuyển mục tiêu kinh doanh thành ưu tiên bảo vệ thực tế. Ví dụ với nền tảng học trực tuyến, tài sản có thể gồm tài khoản học viên, kết quả học tập, dữ liệu thanh toán do bên thứ ba xử lý, mã nguồn, hạ tầng production và tài khoản quản trị.

Các bước thường gặp:

1. Xác định **tài sản, dịch vụ, quy trình và dữ liệu trọng yếu**.
2. Thống nhất **mục tiêu bảo mật**: bảo mật thông tin, toàn vẹn, sẵn sàng, tính truy vết và phục hồi phù hợp.
3. Phân tích các **mối đe dọa**: chiếm tài khoản, lộ API, lạm dụng quyền, chuỗi cung ứng phần mềm, ransomware, sai cấu hình.
4. Xác định rủi ro, độ ưu tiên và **risk appetite/tolerance** theo quyết định của cấp có thẩm quyền.
5. Thiết kế **lộ trình cải tiến** có owner, ngân sách, mốc đánh giá và tiêu chí chứng minh hiệu quả.

Chiến lược không chỉ là danh sách công cụ muốn mua; nó cần giải thích vì sao một khoản đầu tư thay đổi rủi ro của tài sản quan trọng và bằng chứng nào sẽ xác nhận thay đổi đó.

### 5.2. Thiết lập chính sách và control baseline

CISO thường điều phối hoặc phê duyệt theo thẩm quyền các chính sách, tiêu chuẩn và yêu cầu bảo mật áp dụng xuyên hệ thống, ví dụ:

- Identity & access management, MFA, đặc quyền, quản lý tài khoản dịch vụ.
- Quản lý tài sản, cấu hình cloud, phân đoạn mạng, endpoint.
- Secure SDLC, threat modeling, kiểm tra dependency và quản lý secret.
- Logging, giám sát, phát hiện và ứng phó sự cố.
- Backup, phục hồi và duy trì hoạt động kinh doanh.
- Đánh giá bên thứ ba và bảo vệ dữ liệu.
- Quản lý lỗ hổng, đánh giá rủi ro, ngoại lệ và remediation.

Từng control phải được gắn với **mục tiêu**, **chủ sở hữu**, **phạm vi**, **ngưỡng đạt**, **phương pháp đánh giá**, **chu kỳ/trigger đánh giá**, **nguồn bằng chứng**. Nếu chính sách chỉ ghi “phải đảm bảo an toàn”, kỹ sư không biết thực thi ra sao và assessor không thể kết luận một cách đáng tin.

### 5.3. Quản trị rủi ro và ưu tiên đầu tư

CISO xây dựng tiêu chí đánh giá rủi ro phù hợp với bộ khung quản trị rủi ro của tổ chức và đảm bảo risk register có thể hỗ trợ quyết định.

Ví dụ bản ghi rủi ro:

| Trường | Ví dụ |
|---|---|
| Risk ID | RISK-IAM-07 |
| Tài sản | Cổng quản trị production |
| Kịch bản | Token của nhân sự bị lộ, tài khoản sở hữu quyền admin quá rộng |
| Tác động | Sửa/lộ dữ liệu học viên, gián đoạn dịch vụ |
| Control hiện có | SSO/MFA cho người dùng, RBAC, audit log |
| Khoảng trống | Service token không có hạn ngắn; thiếu giám sát thao tác đặc quyền |
| Hướng xử lý | Giới hạn scope, rotation, cảnh báo, review quyền |
| Risk owner | Lãnh đạo phụ trách nền tảng trong phạm vi được ủy quyền |
| Người phối hợp | IAM/Platform owner, Security engineering, CISO |
| Bằng chứng hoàn thành | Policy và cấu hình mới, test từ chối truy cập ngoài quyền, log, retest |
| Trạng thái | Đang xử lý; chưa coi là chấp nhận rủi ro |

Lãnh đạo cần hiểu **rủi ro trước control**, **hiệu quả control**, **rủi ro còn lại** và **giới hạn bằng chứng**. Không nên biến risk register thành bảng chỉ có màu xanh/đỏ nhưng không mô tả kịch bản hoặc người chịu trách nhiệm.

### 5.4. Quản trị chương trình security assurance

Trong phạm vi bài học, đây là trách nhiệm cốt lõi. CISO giúp thiết lập cách tổ chức **chứng minh**, thay vì chỉ **tuyên bố**, rằng mục tiêu bảo mật đang được đáp ứng:

1. Xác định **claim** cần chứng minh, phạm vi, đối tượng sử dụng kết luận và kỳ đánh giá.
2. Thống nhất **yêu cầu và tiêu chí kiểm soát** theo rủi ro và nghĩa vụ áp dụng.
3. Chỉ định **control owner**, người tạo bằng chứng, người thực hiện kiểm thử và người đánh giá.
4. Định nghĩa **test plan**, phương pháp chọn mẫu, độ phủ và điều kiện đạt.
5. Bảo đảm **evidence** đủ nguồn gốc, mới, toàn vẹn, đúng phạm vi và có thể kiểm tra lại.
6. Xem xét **finding, ngoại lệ, rủi ro còn lại** và yêu cầu khắc phục có retest.
7. Báo cáo **kết luận có điều kiện** cho lãnh đạo, đồng thời duy trì theo dõi khi hệ thống thay đổi.

Một báo cáo assurance hữu ích không chỉ trả lời “đã có SAST và pentest chưa?”, mà trả lời “mục tiêu bảo mật quan trọng nào đã được chứng minh ở phạm vi nào, bằng chứng đáng tin đến đâu, điều gì chưa được chứng minh và ai đang xử lý?”.

### 5.5. Quản lý sự cố và khả năng khôi phục

CISO có thể sở hữu hoặc điều phối khung quản lý sự cố: phân cấp, vai trò trực, nghĩa vụ thông báo, điều kiện escalation, giao tiếp khủng hoảng, năng lực điều tra và diễn tập. **Incident commander** trong sự cố cụ thể có thể là người khác, tùy mô hình trực và loại sự cố.

CISO cần xác nhận có cơ chế để:

- Nhận và đánh giá cảnh báo từ SOC, engineering, người dùng và nhà cung cấp.
- Quyết định escalation dựa trên tác động, phạm vi và dấu hiệu ảnh hưởng dữ liệu.
- Phối hợp cô lập, thu hồi secret/token, bảo toàn bằng chứng và hạn chế lan rộng.
- Phối hợp pháp lý, quyền riêng tư, truyền thông, chăm sóc khách hàng theo nghĩa vụ áp dụng.
- Xác nhận điều kiện khôi phục và giám sát nguy cơ tái xâm nhập.
- Chỉ đạo hậu kiểm, root cause analysis và retest control bị thất bại.

Trong khủng hoảng, phân định quyền giữa người chỉ huy kỹ thuật, lãnh đạo nghiệp vụ, pháp lý và CISO phải được chuẩn bị **trước** sự cố để tránh trì hoãn quyết định.

### 5.6. Tuân thủ, audit và bên thứ ba

CISO phối hợp xác định yêu cầu bảo mật có liên quan đến luật, hợp đồng, chính sách và các framework đã chọn áp dụng; các bộ phận Legal/Compliance hỗ trợ xác định nghĩa vụ chính thức. CISO cần bảo đảm:

- Yêu cầu được ánh xạ tới **control** và **evidence owner**.
- Các phát hiện audit có owner, hạn xử lý, kế hoạch và kết quả retest.
- Các báo cáo cho khách hàng hoặc auditor không vượt quá phạm vi bằng chứng.
- Nhà cung cấp trọng yếu được phân loại, đánh giá và theo dõi rủi ro theo quan hệ thực tế.
- Chính sách và bằng chứng được cập nhật khi môi trường pháp lý, hợp đồng hoặc công nghệ thay đổi.

**Compliance** đặt câu hỏi “có đáp ứng các yêu cầu áp dụng không?”, còn **assurance** đặt câu hỏi “bằng chứng có tạo cơ sở tin cậy rằng mục tiêu bảo mật được đạt trong phạm vi xét không?”. CISO phải quản trị cả hai chiều này, không đồng nhất một chứng nhận/báo cáo audit với việc hệ thống an toàn tuyệt đối.

## 6. CISO xác lập accountability như thế nào?

Có nhiệm vụ được giao nhưng không có người chịu trách nhiệm cụ thể thì control dễ trở thành “việc của nhóm bảo mật”. CISO nên thiết lập trách nhiệm theo từng hoạt động.

### 6.1. RACI: ai làm, ai chịu trách nhiệm, ai được tham vấn?

**RACI** là cách xác định:

- **R – Responsible:** người trực tiếp thực hiện công việc.
- **A – Accountable:** người chịu trách nhiệm cuối cùng cho kết quả/quyết định của hoạt động theo cơ cấu ủy quyền.
- **C – Consulted:** người được tham vấn trước hoặc trong khi thực hiện.
- **I – Informed:** người cần được thông báo về kết quả.

Bảng minh họa cho một tổ chức có product, platform, CISO, risk owner và internal audit:

| Hoạt động | CISO/Security | Product hoặc Platform owner | Risk owner/Lãnh đạo được giao | Internal audit |
|---|---|---|---|---|
| Đề xuất tiêu chuẩn bảo mật | R | C | A | I |
| Triển khai MFA cho admin production | C | A/R | I | I |
| Đánh giá control và lập báo cáo assurance | A/R | C, cung cấp evidence | I | I |
| Quyết định chấp nhận rủi ro vượt control baseline | C, khuyến nghị/escalate | R, đề xuất phương án | A | I |
| Khắc phục lỗ hổng dịch vụ | C | A/R | I, nếu ảnh hưởng lớn | I |
| Audit độc lập theo kế hoạch | C, cung cấp hồ sơ | C, cung cấp hồ sơ | I | A/R |

Đây chỉ là **mẫu để thảo luận**, không phải cơ cấu RACI bắt buộc. Trong tổ chức cụ thể, người phê duyệt chính sách có thể là CEO/ủy ban bảo mật, bộ phận GRC có thể đảm nhiệm assessment, còn internal audit báo cáo cho audit committee. Cần xác định **A rõ ràng cho từng công việc**, không để một quyết định quan trọng chỉ có nhiều người “tham gia” nhưng không ai chịu trách nhiệm.

### 6.2. Đặc biệt quan trọng: risk owner và control owner

**Risk owner** chịu trách nhiệm lựa chọn và theo dõi phương án xử lý một rủi ro thuộc hoạt động mình sở hữu. **Control owner** chịu trách nhiệm thiết kế, triển khai hoặc duy trì control cụ thể. Hai vai trò có thể thuộc cùng một người nhưng không nhất thiết.

Ví dụ rủi ro mất dữ liệu của hệ thống học tập:

- Risk owner: lãnh đạo dịch vụ học tập chịu tác động kinh doanh.
- Control owner: platform team vận hành backup và restore.
- Security/CISO: định nghĩa tiêu chí, yêu cầu kiểm chứng và báo cáo mức rủi ro.
- Internal audit: có thể đánh giá độc lập chương trình theo kế hoạch.

Nếu restore test không đạt, CISO phải **escalate và theo dõi xử lý**, nhưng không thể đơn phương tạo ra kết quả restore đạt chỉ bằng cách ký chấp nhận hồ sơ.

## 7. CISO tổ chức chuỗi Claim–Argument–Evidence (CAE)

Một nhiệm vụ trực tiếp của CISO trong security assurance là tạo sự liên kết từ **mục tiêu kinh doanh và rủi ro** tới **claim về kiểm soát bảo mật** và **bằng chứng**.

~~~mermaid
flowchart TD
  A["Mục tiêu bảo mật và tài sản trọng yếu"] --> B["Risk assessment và tiêu chí chấp nhận"]
  B --> C["Security requirement và control baseline"]
  C --> D["Control owner triển khai/vận hành"]
  D --> E["Test, telemetry, evidence"]
  E --> F["Assessor đánh giá claim"]
  F --> G{"Đạt và bằng chứng đủ?"}
  G -->|"Có"| H["CISO tổng hợp assurance và residual risk"]
  G -->|"Không"| I["Finding, owner và remediation"]
  I --> D
  H --> J["Ban lãnh đạo quyết định ưu tiên/xử lý"]
  J --> K["Theo dõi thay đổi và tái đánh giá"]
  K --> B
~~~

### 7.1. Viết claim phù hợp

Ví dụ, từ mục tiêu “tránh truy cập trái phép vào dữ liệu học viên”, CISO có thể yêu cầu claim cụ thể:

> Trong kỳ đánh giá, các tài khoản người dùng có quyền quản trị production thuộc phạm vi xác định được cấp quyền qua quy trình phê duyệt, yêu cầu xác thực đa yếu tố và được rà soát quyền theo chính sách.

Claim này cần thêm **phạm vi** (tài khoản tương tác, emergency, workload có/không bao gồm), **tiêu chí**, **thời gian**, **lý do các control đủ thích hợp** và **danh sách bằng chứng**. Nếu thiếu các yếu tố này, người đánh giá không biết đang phải chứng minh điều gì.

### 7.2. Hồ sơ assurance mà CISO có thể yêu cầu

Ví dụ minh họa cấu trúc hồ sơ, không phải schema bắt buộc của một chuẩn:

~~~yaml
assurance_record_id: SA-ADMIN-01
claim: "Truy cập quản trị production được kiểm soát và có thể truy vết"
scope:
  assets: ["production-admin-console", "identity-provider"]
  accounts: "Tài khoản con người có quyền admin production"
period: "Quý đánh giá nội bộ đã xác định"
criteria:
  - "Các quyền admin có chủ sở hữu và hồ sơ phê duyệt"
  - "MFA được enforce trên các đường đăng nhập thuộc phạm vi"
  - "Quyền không còn cần thiết được thu hồi theo chính sách"
controls:
  - id: IAM-01
    owner: "IAM team"
  - id: IAM-02
    owner: "Platform operations"
evidence:
  - "Bản xuất danh sách tài khoản, role và MFA policy kèm thời gian"
  - "Ticket cấp quyền và thu hồi quyền theo mẫu xác định"
  - "Kết quả thử truy cập thiếu MFA, audit log liên quan"
assessment:
  assessor: "Security assurance reviewer"
  status: "Chưa kết luận trước khi kiểm tra"
  limitations: "Service accounts và break-glass được đánh giá riêng"
risk_owner: "Chủ sở hữu dịch vụ trong phạm vi phê duyệt"
reported_by: "CISO"
~~~

CISO cần đặt câu hỏi: **Bằng chứng có được lấy từ nguồn chính thức không? Có chứng minh control hoạt động suốt kỳ không? Một ảnh chụp có đủ không? Có kiểm tra các đường bypass và tài khoản ngoại lệ không? Có ai độc lập với người vận hành control thực hiện đánh giá không?**

### 7.3. Ba lớp kiểm tra trước khi báo cáo “đạt”

| Lớp đánh giá | Câu hỏi | Ví dụ |
|---|---|---|
| **Thiết kế (design)** | Control có xử lý đúng rủi ro và điều kiện thất bại? | Tiêu chuẩn IAM yêu cầu phê duyệt, MFA, thu hồi và phát hiện thao tác đặc quyền |
| **Triển khai (implementation)** | Chính sách có hiện diện và áp dụng đúng với production không? | Cấu hình IdP, IAM roles, kết quả kiểm thử truy cập |
| **Hiệu quả vận hành (operating effectiveness)** | Control có vận hành ổn định theo tiêu chí trong kỳ không? | Mẫu phê duyệt/thu hồi, log, review quyền, evidence xử lý ngoại lệ |

Không thể suy diễn hiệu quả vận hành của cả quý từ một ảnh chụp cấu hình. Tùy rủi ro và loại control, cần log, lịch sử thay đổi, mẫu giao dịch, diễn tập hoặc kiểm thử theo kỳ.

## 8. Quy trình CISO quản trị chương trình assurance liên tục

Một chương trình thực tế không thể dựa vào báo cáo làm một lần mỗi năm. CISO cần xây nhịp phối hợp giữa **phát triển – vận hành – đánh giá – xử lý**.

| Nhịp/kích hoạt | Hoạt động CISO tổ chức | Bằng chứng/đầu ra |
|---|---|---|
| Đầu kỳ chiến lược | Rà soát tài sản, mục tiêu, risk appetite được phê duyệt và nguồn lực | Security strategy, risk register, baseline, owner |
| Khi thiết kế hệ thống | Yêu cầu threat model, tiêu chí bảo mật, thiết kế control phù hợp | Architecture review, threat model, action items |
| Mỗi thay đổi có rủi ro đáng kể | Kiểm tra kết quả bảo mật của change/deploy và quyền chấp thuận | Pull request, pipeline result, change record, approval |
| Hằng ngày/tuần theo rủi ro | Theo dõi lỗ hổng, cảnh báo, thất bại control, finding trọng yếu | Dashboard có provenance, ticket, incident log |
| Định kỳ theo control | Đánh giá quyền, phục hồi, hoạt động log/alert, compliance evidence | Access review, restore test, control assessment |
| Khi có sự cố/ngoại lệ | Đánh giá tác động, escalation, phương án xử lý và retest | Incident record, risk decision, remediation evidence |
| Trước các cuộc họp quản trị | Tổng hợp tình trạng và xu hướng rủi ro, yêu cầu quyết định | Executive security report, exceptions, decisions |
| Khi thay đổi lớn | Tái xác định scope, yêu cầu và mức tin cậy của assurance | Updated risk/control/evidence mapping |

“Liên tục” nghĩa là **bằng chứng và quyết định được làm mới theo tốc độ thay đổi/rủi ro**; không bắt buộc mọi control đều phải được kiểm thử mỗi phút. Ví dụ, policy-as-code có thể chạy mỗi deploy, còn diễn tập khôi phục và review quyền chạy theo chu kỳ phù hợp với độ trọng yếu.

### 8.1. CISO quyết định ưu tiên kiểm thử ra sao?

Xác định mức ưu tiên bằng cách xem xét:

- **Tác động kinh doanh và dữ liệu:** hệ thống chứa thông tin nhạy cảm hay hỗ trợ dịch vụ cốt lõi?
- **Khả năng khai thác và mức phơi bày:** endpoint Internet-facing, quyền admin, phụ thuộc bên thứ ba?
- **Lịch sử control:** có sai lệch lặp lại, evidence không đủ, pipeline dễ bypass?
- **Thay đổi mới:** release lớn, migration, thay IdP, nhà cung cấp hoặc chính sách?
- **Nghĩa vụ và thời hạn:** audit, cam kết khách hàng, thời hạn xử lý sự cố?
- **Sự bất định:** thiếu inventory, thiếu log hoặc không thể xác định control owner?

Một điểm yếu có tác động lớn nhưng ít dữ liệu đo lường có thể cần ưu tiên đánh giá trước một control có dashboard đẹp nhưng rủi ro thấp.

### 8.2. Cơ chế xử lý finding có thể kiểm chứng

CISO phải bảo đảm một finding có đường đi khép kín:

1. **Ghi phát hiện:** tiêu chí kỳ vọng, điều kiện quan sát, bằng chứng, hệ thống bị ảnh hưởng.
2. **Đánh giá tác động:** kết nối với kịch bản rủi ro và độ ưu tiên.
3. **Giao owner:** ai sửa nguyên nhân, ai quyết định chi phí/ưu tiên, ai theo dõi?
4. **Lập phương án:** sửa kỹ thuật, đổi quy trình hoặc control bù trừ có thời hạn.
5. **Theo dõi hạn và ngoại lệ:** ghi quyết định, thẩm quyền, residual risk và ngày tái đánh giá.
6. **Retest độc lập phù hợp:** xác nhận control thực sự hoạt động trong phạm vi từng fail.
7. **Cập nhật báo cáo:** điều chỉnh kết luận claim và risk register, đóng finding khi đủ điều kiện.

**Lưu ý:** “đã giao ticket” và “đã triển khai thay đổi” không đồng nghĩa “finding đã được khắc phục có hiệu quả”. Cần evidence của trạng thái **sau sửa** và kết quả retest.

## 9. Báo cáo nào giúp lãnh đạo ra quyết định?

CISO cần chuyển dữ liệu kỹ thuật thành **rủi ro, tác động, trạng thái kiểm soát, độ tin cậy và yêu cầu quyết định**. Báo cáo nhiều biểu đồ nhưng không chỉ ra việc phải làm sẽ khó giúp lãnh đạo ưu tiên.

### 9.1. Cấu trúc executive security report

Một báo cáo tóm tắt có thể gồm:

1. **Phạm vi và kỳ báo cáo:** tổ chức/hệ thống/dữ liệu được xem xét; phần nào chưa được đánh giá.
2. **Rủi ro trọng yếu:** tình huống có thể xảy ra, tác động đến sản phẩm/khách hàng, thay đổi so với kỳ trước.
3. **Assurance theo mục tiêu:** control đạt, không đạt, chưa đủ bằng chứng, giới hạn của phép thử.
4. **Sự cố và xu hướng:** sự cố đáng kể, thời gian xử lý, nguyên nhân lặp lại và rủi ro tồn đọng.
5. **Finding và ngoại lệ:** số tồn đọng theo mức ảnh hưởng, owner, hạn, retest và quyết định cần cấp trên.
6. **Hiệu quả đầu tư:** chương trình nào đang giảm rủi ro hoặc cải thiện độ phủ control.
7. **Yêu cầu quyết định:** ngân sách, nhân lực, chấp nhận rủi ro trong thẩm quyền, thay đổi chính sách hay trì hoãn release.
8. **Bằng chứng liên kết:** reference tới kết quả kiểm thử, risk register, change history, audit report để người nhận có thể truy vết.

### 9.2. Phân biệt metric với kết luận

| Chỉ số | Cách dùng hữu ích | Ngộ nhận cần tránh |
|---|---|---|
| Tỷ lệ tài sản trọng yếu có control owner | Độ phủ trách nhiệm | Có tên owner không chứng minh control hiệu quả |
| Tỷ lệ control có evidence hợp lệ trong kỳ | Mức sẵn sàng cho assurance | Evidence cũ, sai phạm vi vẫn có thể làm chỉ số tăng |
| Tỷ lệ thay đổi production qua security gate | Độ bao phủ kiểm tra trước deploy | Gate có thể bỏ sót kịch bản hoặc bị bypass |
| Finding nghiêm trọng quá hạn | Năng lực giảm thiểu rủi ro | Đóng ticket khi chưa retest sẽ làm đẹp số liệu giả |
| Tỷ lệ restore test đạt RPO/RTO | Mức tin cậy phục hồi | Cần kiểm tra đúng loại dữ liệu và tính toàn vẹn |
| Thời gian phát hiện/phản ứng sự cố | Hiệu quả quy trình phát hiện/ứng phó | Chỉ đo sự cố đã được nhận diện; thiếu telemetry tạo thiên lệch |
| Ngoại lệ control quá hạn | Rủi ro được tạm chấp nhận đang tích lũy | Ít ngoại lệ có thể do thiếu cơ chế khai báo |

Ví dụ, **“98% control đạt”** không có nghĩa còn 2% rủi ro: một control trọng yếu thất bại có thể tạo hậu quả lớn hơn nhiều control ít quan trọng đang đạt. CISO phải báo cáo **trọng số rủi ro, mức ảnh hưởng và giới hạn dữ liệu**, tránh một điểm tổng hợp thiếu ngữ cảnh.

## 10. Tình huống thực tế: CISO và quyết định ra mắt tính năng

### 10.1. Bối cảnh

Một nền tảng học trực tuyến chuẩn bị ra mắt tính năng cho phép giảng viên tải lên và xuất kết quả học tập của học viên. Backend gồm nhiều service Java, lưu file trên object storage và có API quản trị. Nhóm sản phẩm muốn phát hành trong tuần để phục vụ hợp đồng mới.

Kết quả đánh giá cho thấy:

- Endpoint xuất dữ liệu mới có bài kiểm thử chức năng nhưng **chưa có test authorization cho truy cập chéo lớp học**.
- Chính sách object storage đã được review, song chưa có bằng chứng kiểm tra **trạng thái cấu hình production sau triển khai**.
- Dịch vụ logging nhận log API, nhưng chưa xác nhận đủ thông tin để phát hiện **xuất dữ liệu số lượng bất thường**.
- Product owner đề nghị “phát hành trước, bổ sung kiểm thử tuần sau”.

CISO không nên chỉ trả lời “đồng ý/không đồng ý” dựa trên cảm tính. Cần xây dựng phương án có bằng chứng và cơ chế quyết định minh bạch.

### 10.2. Phân tích theo mục tiêu – rủi ro – control

| Mục tiêu bảo mật | Rủi ro nếu phát hành | Control và phép kiểm thử đề xuất | Bằng chứng cần có |
|---|---|---|---|
| Giảng viên chỉ truy cập học viên thuộc phạm vi được phép | Truy cập chéo lớp học/tenant, lộ dữ liệu | Server-side authorization; test deny trên identity khác lớp/tenant | Test report, policy, kết quả chạy trong build dùng để phát hành |
| File xuất không truy cập công khai ngoài chủ thể được cấp quyền | Lộ object hoặc URL chia sẻ quá rộng | Private bucket, least privilege, kiểm tra URL/token expiry, kiểm tra production configuration | IAM/bucket policy export, kết quả kiểm tra truy cập từ ngoài scope |
| Hành vi xuất dữ liệu được truy vết | Không thể điều tra hoặc phát hiện lạm dụng | Audit log sự kiện xuất, metadata an toàn, alert theo hành vi rủi ro | Log mẫu, test alert, ticket routing |
| Lỗi mới có thể được kiểm soát | Không cô lập được chức năng xuất file | Feature flag, canary, rollback/disable có điều kiện | Kế hoạch phát hành, thử tắt chức năng, người chịu trách nhiệm |

### 10.3. Quyết định và trách nhiệm

**Hướng xử lý CISO đề xuất:** ưu tiên sửa/test authorization trước khi mở tính năng cho người dùng thực; kiểm tra cấu hình storage production; xác nhận tối thiểu logging cần thiết; nếu còn khoảng trống, giảm phạm vi phát hành hoặc giữ tính năng sau feature flag đến khi có bằng chứng.

**Ai quyết định?** Theo cơ chế đã được phê duyệt, product/risk owner và cấp lãnh đạo phù hợp quyết định chấp nhận rủi ro còn lại hoặc trì hoãn phát hành. CISO mô tả rủi ro, khuyến nghị, điều kiện và ghi nhận ý kiến chuyên môn; security gate có thể có quyền chặn theo chính sách nội bộ. Không nên dùng việc “CISO đã cảnh báo” để tự miễn trách nhiệm cho bộ phận tiếp tục phát hành.

**Khi nào có thể coi một finding đã đóng?** Khi team kỹ thuật sửa và assessor kiểm tra lại điều kiện từng thất bại, lưu evidence gắn với phiên bản release và cập nhật hồ sơ rủi ro. Nếu chỉ có lời hứa “sẽ test sau”, trạng thái thích hợp vẫn là **chưa đủ bằng chứng** hoặc **không đạt** theo tiêu chí xác định.

### 10.4. Ví dụ quyết định được ghi bằng văn bản

~~~text
Decision ID: REL-2026-EXAMPLE
Scope: Export learning results API – production release
Risk: Unauthorized cross-class access to learner records
Finding: Missing authorization regression evidence
Business owner: Learning Platform Product Owner
Control owner: Backend/API Team
CISO recommendation: Hold unrestricted release until test passes
Decision authority: Designated risk owner / release approver
Decision: Limited internal rollout behind feature flag
Conditions:
  - No customer traffic until authorization tests pass
  - Test object storage policy in production-equivalent environment
  - Review audit log before external rollout
Reassessment trigger: New deployment, scope expansion, test failure
Evidence links: Test report, change ticket, config snapshot
~~~

Tên và thời điểm trong ví dụ chỉ minh họa một hồ sơ quản trị. Hồ sơ thực tế cần người phê duyệt, ngày hiệu lực, thời hạn ngoại lệ và dấu vết công cụ quản lý của tổ chức.

## 11. Khi xảy ra sự cố: CISO lãnh đạo ở cấp độ nào?

Giả sử SOC phát hiện truy cập bất thường vào file xuất dữ liệu. Có ba lớp quyết định đồng thời:

- **Kỹ thuật tức thời:** incident commander điều phối cô lập endpoint, thu hồi token, bảo vệ log và kiểm tra dữ liệu bị ảnh hưởng; các owner triển khai hành động.
- **Rủi ro và nghĩa vụ:** CISO phối hợp risk owner, Legal/Privacy xác định tác động, mức độ nghiêm trọng, yêu cầu thông báo và giới hạn bằng chứng.
- **Quản trị và truyền thông:** lãnh đạo được ủy quyền quyết định ưu tiên kinh doanh, phân bổ nguồn lực, phương án phục hồi và thông tin bên ngoài theo quy trình.

CISO cần tránh hai cực đoan: **điều khiển trực tiếp mọi lệnh kỹ thuật** khiến ứng phó bị tắc, hoặc **chỉ nhận báo cáo tổng hợp cuối ngày** nên không thể escalate khi rủi ro diễn biến nghiêm trọng. Quy trình phải nói rõ ngưỡng nào cần sự tham gia của CISO và ai thay thế khi vắng mặt.

### 11.1. Điều kiện mở lại dịch vụ sau sự cố

Một checklist quyết định có thể yêu cầu:

1. Đường xâm nhập đã được cô lập hoặc giảm thiểu đến mức chấp nhận.
2. Credential/token bị ảnh hưởng được xử lý, quyền bất thường được rà soát.
3. Bản build, cấu hình và dữ liệu phục hồi đã được xác minh tính toàn vẹn ở mức phù hợp.
4. Kết quả test lại control từng thất bại đã được lưu.
5. Giám sát bổ sung có khả năng phát hiện hành vi tái diễn.
6. Rủi ro còn lại được trình cấp có thẩm quyền, cùng giới hạn thông tin hiện có.
7. Có owner theo dõi hậu sự cố, remediation và bài học cải tiến.

Không nên dùng sự trở lại của chỉ số uptime làm bằng chứng duy nhất rằng trạng thái bảo mật đã được khôi phục.

## 12. Những sai lầm trong thực hiện vai trò CISO

### “CISO là người duy nhất sở hữu mọi rủi ro bảo mật”

Không chính xác. Rủi ro gắn với tài sản và hoạt động kinh doanh cần chủ sở hữu và thẩm quyền xử lý tương ứng. CISO giúp đánh giá, đề xuất, giám sát và escalate; quyền chấp nhận rủi ro phải được phân cấp rõ.

### “Đội bảo mật làm hết, kỹ sư chỉ phát triển tính năng”

Nếu engineering/platform không sở hữu control trong code, cloud và vận hành, các finding sẽ không được sửa triệt để. CISO phải thiết lập accountability cho tuyến triển khai.

### “Đạt audit hoặc chứng nhận nghĩa là không cần đánh giá thêm”

Audit và chứng nhận có phạm vi, tiêu chí, thời kỳ và giới hạn. Mối đe dọa, cấu hình, quyền truy cập và môi trường kinh doanh vẫn thay đổi, nên assurance phải được làm mới.

### “Càng nhiều lỗ hổng được báo cáo là chương trình càng kém”

Số finding còn phụ thuộc độ phủ và chất lượng phát hiện. Cần xem **mức rủi ro, thời gian khắc phục, tỷ lệ tái diễn và bằng chứng retest**.

### “CISO luôn có quyền dừng mọi release”

Không mặc nhiên. Thẩm quyền security gate, quyền veto, escalation và người quyết định ngoại lệ phụ thuộc quy chế cụ thể. Điều cốt lõi là ghi rõ quyền hạn và trách nhiệm ra quyết định.

### “CISO có thể tự ký xác nhận mọi control do nhóm mình vận hành”

Tự đánh giá có thể hữu ích cho giám sát vận hành, nhưng kết luận độc lập đòi hỏi cơ chế review hoặc audit đủ độc lập với người thực hiện; đồng thời phải công khai mức độ độc lập và giới hạn bằng chứng.

### “Không có sự cố nghĩa là bảo mật tốt”

Có thể tổ chức chưa phát hiện được sự cố. CISO cần đánh giá sức khỏe hệ thống logging, khả năng phát hiện, coverage và các phép thử kiểm soát.

## 13. Xây chương trình CISO từ điểm xuất phát chưa trưởng thành

Với một tổ chức mới có các biện pháp bảo mật rời rạc, CISO có thể thiết kế lộ trình **30–60–90 ngày minh họa**. Lộ trình thực tế cần điều chỉnh theo quy mô, tình trạng sự cố, tài sản trọng yếu, năng lực pháp lý và nguồn lực.

| Giai đoạn | Trọng tâm | Đầu ra có thể kiểm chứng |
|---|---|---|
| **30 ngày đầu** | Hiểu nghiệp vụ, tài sản, người sở hữu, sự cố hiện hữu, chính sách và nghĩa vụ trọng yếu | Inventory sơ bộ, threat/risk register ban đầu, danh sách gap nghiêm trọng, tuyến báo cáo |
| **Ngày 31–60** | Thống nhất baseline và owner; kiểm chứng các control quan trọng như đặc quyền, backup, logging, deploy | Control map, RACI, test plan, evidence nguồn, kế hoạch remediation ưu tiên |
| **Ngày 61–90** | Triển khai nhịp assurance, báo cáo điều hành, retest gap và diễn tập một kịch bản quan trọng | Dashboard có scope, claim/evidence records, danh sách finding/ngoại lệ, quyết định và kết quả kiểm chứng |

Trình tự là ví dụ định hướng; nếu có sự cố đang diễn ra hoặc rủi ro khẩn cấp, cần xử lý ngay trong phạm vi thẩm quyền, không đợi đến mốc ngày dự kiến.

### 13.1. Những câu hỏi CISO nên đặt trong cuộc họp với hệ thống owner

- Dịch vụ này phục vụ mục tiêu kinh doanh nào? Dữ liệu và hành động nhạy cảm nhất là gì?
- Ai là owner của rủi ro, ai có quyền thay đổi production và ai phê duyệt?
- Lỗi an ninh mạng hoặc sai sót vận hành nào có thể gây tổn thất lớn nhất?
- Control nào đang giảm rủi ro? Có đường bypass hay ngoại lệ đặc biệt không?
- Bằng chứng mới nhất chứng minh control **đang hoạt động**, lấy từ đâu?
- Nếu control thất bại lúc nửa đêm, ai được báo, ai được phép xử lý, mất bao lâu?
- Lần kiểm thử phục hồi, kiểm tra phân quyền hoặc diễn tập sự cố gần nhất ra sao?
- Finding quan trọng nhất đang quá hạn là gì? Vì sao chưa được khắc phục?
- Khi thêm tính năng/nhà cung cấp/loại dữ liệu mới, ai cập nhật scope assurance?

Một hệ thống owner có thể trả lời một số câu bằng “chưa biết”. Đó là tín hiệu cần **đo/kiểm tra bổ sung**, không nên biến thành kết luận “đạt” hay “không có rủi ro” dựa trên suy đoán.

## 14. Bài tập áp dụng

### Bài tập 1 – Chỉ định trách nhiệm

Một ứng dụng Java có endpoint quản trị bị cấu hình sai. Chỉ có CISO biết về sự cố; team backend nói network do platform quản, platform nói endpoint do backend quản, product owner muốn ra mắt đúng hạn.

Hãy phân định cho từng việc: **(a) xác định tác động nghiệp vụ; (b) sửa cấu hình và authorization; (c) đánh giá rủi ro; (d) quyết định hoãn/phát hành có điều kiện; (e) kiểm thử lại; (f) báo cáo cho ban điều hành**.

**Gợi ý:** Product/risk owner xử lý tác động và quyết định trong thẩm quyền; backend/platform là control owner tương ứng; security assurance thực hiện hoặc điều phối đánh giá độc lập phù hợp; CISO đưa khuyến nghị và báo cáo rủi ro; người có quyền release phải được chỉ định rõ. Nếu hai team đều từ chối trách nhiệm, việc đầu tiên là gắn owner cho control thay vì chỉ trao đổi thêm qua email.

### Bài tập 2 – Đánh giá tính đáng tin của báo cáo

CISO được trình dashboard:

- 100% policy đã được phê duyệt.
- 95% hệ thống được bật vulnerability scanner.
- 0 sự cố nghiêm trọng được ghi nhận trong tháng.
- 20 finding đã đóng.

Hãy nêu **ít nhất sáu câu hỏi** trước khi kết luận mức assurance.

**Gợi ý câu hỏi:** Policy có được triển khai không? 5% không scan là hệ thống gì? Scanner có xác thực đầy đủ và chạy đúng thời kỳ không? Khả năng thu thập log/alert có hoạt động không? Có thử phát hiện sự cố không? Các finding có kết quả retest hay chỉ đóng ticket? Phạm vi còn thiếu là gì? Có các rủi ro trọng yếu khác không được đo? Có đánh giá độc lập nào đối chiếu được dashboard không?

### Bài tập 3 – Viết mini assurance brief cho CISO

Giả sử công ty yêu cầu: “Chỉ nhân sự phù hợp mới được quyền xuất dữ liệu học viên”.

Hãy tạo mini brief một trang có các mục:

1. **Claim:** một câu có phạm vi và kỳ kiểm tra.
2. **Risk scenario:** một đường tấn công hoặc lỗi vận hành cụ thể.
3. **Control owner và risk owner:** ghi vai trò, không chỉ tên đội chung chung.
4. **Control:** xác thực, phân quyền theo đối tượng, log, review quyền.
5. **Evidence:** các nguồn chính thức và phép test authorization/negative test.
6. **Kết quả đánh giá:** đạt, không đạt hay chưa đủ bằng chứng; căn cứ.
7. **Finding và action:** owner, hạn và phép retest.
8. **Decision needed:** có phải trình cấp quản trị hay không, dựa trên điều kiện nào.

Một brief tốt sẽ giúp CISO báo cáo **rủi ro còn lại và quyết định cần đưa ra**, đồng thời giúp kỹ sư biết rõ tiêu chí và bằng chứng cần bổ sung.

## 15. Ghi nhớ

- **CISO là người lãnh đạo chức năng bảo mật và điều phối assurance ở cấp tổ chức**, chuyển rủi ro thành chiến lược, tiêu chí, control, evidence và quyết định.
- CISO cần **quyền hạn, nguồn lực, kênh escalation và trách nhiệm rõ ràng**; quyền chấp nhận rủi ro, chặn release hoặc phê duyệt ngoại lệ tùy cơ chế ủy quyền.
- **Risk owner** chịu trách nhiệm xử lý/chấp nhận rủi ro trong thẩm quyền; **control owner** chịu trách nhiệm vận hành control; **assessor/auditor** đánh giá bằng chứng với mức độc lập thích hợp.
- Kết luận bảo mật phải dựa trên **claim → argument → evidence**, phạm vi, kỳ đánh giá, phép thử, finding, giới hạn và rủi ro còn lại.
- CISO tốt không chỉ đo công cụ, chứng nhận hay số ticket; họ tổ chức **đánh giá và cải tiến liên tục**, gắn việc khắc phục và retest với hoạt động phát triển, vận hành.


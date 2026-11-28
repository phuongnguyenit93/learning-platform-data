# Third-party risk: Quản lý rủi ro từ bên thứ ba bằng bằng chứng kiểm chứng được

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Giải thích **third-party risk**, phân biệt rủi ro từ nhà cung cấp trực tiếp với rủi ro **fourth-party/nth-party**, đồng thời xác định các ranh giới tin cậy và tài sản chịu ảnh hưởng.
2. Xây dựng danh mục bên thứ ba, phân loại mức độ quan trọng của quan hệ hợp tác, nhận diện kịch bản rủi ro về bảo mật, quyền riêng tư, tính sẵn sàng, chuỗi cung ứng và tuân thủ.
3. Đánh giá **inherent risk** và **residual risk** bằng tiêu chí nhất quán, phân biệt giả định, đánh giá dựa trên bằng chứng và quyết định chấp nhận rủi ro.
4. Thu thập, kiểm tra và diễn giải chứng cứ từ questionnaire, SOC 2, chứng nhận ISO/IEC 27001, báo cáo pentest, kiến trúc, hợp đồng, cấu hình và kết quả thử nghiệm.
5. Lựa chọn security controls tại cả phía khách hàng và nhà cung cấp: phân quyền, bảo vệ dữ liệu, giám sát, điều khoản hợp đồng, ứng phó sự cố, khả năng phục hồi và chấm dứt quan hệ.
6. Tổ chức vòng đời assurance liên tục từ lựa chọn, onboarding, vận hành, tái đánh giá đến offboarding, với chuỗi **claim → control → test → evidence → finding → decision → retest**.

## 1. Third-party risk là gì?

**Third-party risk** là rủi ro phát sinh khi tổ chức phụ thuộc vào một pháp nhân, sản phẩm, dịch vụ hoặc hoạt động được cung cấp bởi một bên ngoài tổ chức. Sự phụ thuộc này có thể gây tác động đến **bí mật dữ liệu (confidentiality), tính toàn vẹn (integrity), tính sẵn sàng (availability), quyền riêng tư, vận hành, pháp lý, uy tín và khả năng thực hiện mục tiêu kinh doanh**.

Ví dụ: hệ thống bán hàng sử dụng nhà cung cấp thanh toán, dịch vụ email SaaS, kho mã nguồn, thư viện mã mở, nhà cung cấp cloud, công cụ support có quyền truy cập production hoặc công ty xử lý dữ liệu. Những bên này mở rộng **attack surface** và ảnh hưởng đến khả năng kiểm soát của tổ chức.

Trong mô-đun **SECURITY_SECURITY_ASSURANCE**, third-party assurance là cách đánh giá có bằng chứng rằng rủi ro do phụ thuộc bên ngoài được quản lý phù hợp: từ phân tích rủi ro, đặt yêu cầu và controls, thẩm định trước hợp tác, giám sát, audit đến khắc phục phát hiện và tái đánh giá khi điều kiện thay đổi.

Một tuyên bố “nhà cung cấp an toàn vì có chứng nhận” là quá rộng. Một tuyên bố có thể kiểm chứng hơn là:

> Nhà cung cấp A chỉ nhận dữ liệu đã được phân loại và cho phép, tài khoản tích hợp được giới hạn quyền, các controls liên quan nằm trong phạm vi chứng cứ có hiệu lực, sự cố được thông báo theo cam kết và khả năng thu hồi quyền/xóa dữ liệu đã được kiểm tra.

### 1.1. Third-party, fourth-party và nth-party

| Thuật ngữ | Quan hệ | Ví dụ |
|---|---|---|
| **First party** | Tổ chức đang đánh giá rủi ro đối với hệ thống và hoạt động của chính mình. | Doanh nghiệp vận hành cổng đặt hàng. |
| **Second party** | Tùy lĩnh vực có thể là khách hàng hoặc đối tác trong quan hệ trực tiếp; thuật ngữ này không phổ quát trong TPRM. | Khách hàng ký hợp đồng với doanh nghiệp. |
| **Third party** | Nhà cung cấp/đối tác bên ngoài có quan hệ trực tiếp với tổ chức. | SaaS hỗ trợ khách hàng, MSP, nhà cung cấp cloud. |
| **Fourth party** | Bên mà third party sử dụng để cung cấp dịch vụ cho tổ chức. | SaaS A đặt hạ tầng tại cloud B. |
| **Nth party** | Các phụ thuộc sâu hơn trong chuỗi cung ứng, có thể không được khách hàng trực tiếp quản lý. | Cloud B dùng dịch vụ DNS/CND/hạ tầng khác. |

Cách đánh số là **cách nhìn từ tổ chức đang đánh giá**, không phải một thuộc tính cố định của doanh nghiệp. Một nhà cung cấp có thể là third party đối với tổ chức này và fourth party đối với tổ chức khác.

Không nên đánh đồng mọi thư viện open-source với một “vendor” có hợp đồng. Dependency phần mềm mã mở thuộc **software supply-chain risk** và cần các controls như inventory/SBOM, provenance, vulnerability management, license review và cơ chế cập nhật. Trong một số trường hợp, nó cũng nằm trong phạm vi quản trị phụ thuộc bên ngoài rộng hơn.

### 1.2. Rủi ro chuyển giao không làm trách nhiệm biến mất

Khi dùng nhà cung cấp cloud hoặc SaaS, tổ chức có thể chuyển một phần **hoạt động vận hành** nhưng vẫn chịu trách nhiệm đối với dữ liệu, quyền truy cập, cấu hình tích hợp, quản trị hợp đồng, yêu cầu pháp lý và rủi ro tồn dư theo phạm vi trách nhiệm của mình.

Ví dụ, SaaS có khả năng mã hóa dữ liệu trong hệ thống của họ không thay thế nghĩa vụ của khách hàng phải cấu hình SSO/MFA, phân quyền tài khoản, giới hạn nội dung tải lên, cấu hình retention và kiểm soát API token nếu các phần này thuộc trách nhiệm của khách hàng.

## 2. Từ phụ thuộc kinh doanh đến ranh giới tin cậy

### 2.1. Bắt đầu bằng bản đồ luồng dữ liệu và quyền

Trước khi gửi questionnaire, phải hiểu **nhà cung cấp thực sự làm gì**:

- Dịch vụ nào phụ thuộc họ? Có phải thành phần của đường giao dịch thiết yếu không?
- Họ xử lý, lưu, xem hoặc truyền dữ liệu gì? Dữ liệu có chứa thông tin khách hàng, hồ sơ nhân sự, bí mật kinh doanh, khóa API hay payment metadata?
- Họ có thể truy cập production, source code, CI/CD, endpoint, mạng nội bộ, tài khoản cloud hoặc hệ thống quản trị danh tính không?
- Họ kết nối bằng API, OAuth, VPN, agent, webhook, SDK, trình duyệt hay quyền quản trị trực tiếp?
- Họ lưu dữ liệu ở khu vực nào, có thuê nhà thầu phụ/subprocessor nào và có thể chuyển dữ liệu đi đâu?
- Khi nhà cung cấp ngừng hoạt động hoặc bị compromise, chức năng nào bị ảnh hưởng và trong bao lâu?
- Tổ chức có thể rút quyền, đổi nhà cung cấp, xuất dữ liệu và tiếp tục hoạt động bằng cách nào?

Sơ đồ mẫu:

~~~mermaid
flowchart LR
    USER["Khách hàng"] --> APP["Order API"]
    APP --> DB["Database nội bộ"]
    APP --> V["SaaS phân tích sự kiện"]
    V --> CLOUD["Cloud hạ tầng của SaaS"]
    V --> SUB["Nhà thầu phụ hỗ trợ"]
    IAM["IdP / IAM nội bộ"] --> APP
    IAM --> V
    OPS["Đội vận hành"] --> IAM
    V -.->|"API / webhook"| APP
~~~

Các mũi tên minh họa quan hệ phụ thuộc hoặc luồng thông tin cần đánh giá; không mặc nhiên cho phép truy cập hai chiều. Với mỗi mối liên kết, ghi **định danh, dữ liệu, loại quyền, giao thức, tần suất, encryption, logging và owner**.

### 2.2. Những dạng rủi ro cần nhận diện

| Nhóm | Tình huống ví dụ | Tài sản/tác động |
|---|---|---|
| **Data confidentiality/privacy** | Dữ liệu khách hàng bị lộ từ SaaS hoặc nhà thầu phụ. | Thông tin cá nhân, bí mật thương mại, nghĩa vụ bảo vệ dữ liệu. |
| **Identity/access** | Tài khoản vendor có quyền admin production không kiểm soát. | Leo thang quyền, lateral movement và mất dấu truy vết. |
| **Integrity/supply chain** | Bản cập nhật SDK hoặc agent bị chèn mã độc. | Thay đổi chức năng, truy cập trái phép, mã thực thi trong ứng dụng. |
| **Availability/concentration** | Một nhà cung cấp duy nhất ngừng hoạt động kéo theo nhiều dịch vụ. | Gián đoạn doanh thu, chuỗi cung ứng và khách hàng. |
| **Cyber incident response** | Vendor phát hiện rò rỉ nhưng thông báo chậm; thiếu log để điều tra. | Kéo dài thời gian phát hiện, containment và thông báo. |
| **Fourth-party** | Nhà thầu phụ phụ trách backup/hosting của vendor bị mất quyền truy cập. | Phục hồi chậm, luồng dữ liệu không dự tính. |
| **Compliance/contractual** | Dữ liệu được xử lý ở địa điểm hoặc mục đích ngoài thỏa thuận. | Vi phạm chính sách, hợp đồng hoặc quy định áp dụng. |
| **Financial/strategic** | Vendor ngừng kinh doanh, đổi điều khoản hoặc tăng giá mạnh. | Vendor lock-in, migration khó, mất dịch vụ. |
| **Operational change** | Vendor thay endpoint, schema hoặc cấu hình bảo mật, làm tích hợp bị lỗi. | Sai dữ liệu, gián đoạn, mất telemetry và khả năng audit. |

Các mục trên phải gắn với **threat scenario cụ thể**, không chỉ đánh dấu ô “vendor security = medium”.

## 3. Lập danh mục và phân tầng nhà cung cấp

### 3.1. Third-party inventory tối thiểu

Mỗi mối quan hệ nên có một định danh ổn định và dữ liệu quản lý:

| Trường | Ví dụ | Vì sao cần |
|---|---|---|
| **vendor_id / legal_entity** | VEN-014, Công ty cung cấp SaaS A | Tránh nhầm tên sản phẩm và pháp nhân chịu trách nhiệm. |
| **service/product** | SaaS phân tích mua hàng | Xác định phụ thuộc đang sử dụng. |
| **business_owner** | Owner của nhóm thương mại điện tử | Có người chịu trách nhiệm đánh giá và xử lý rủi ro. |
| **technical_owner** | Nhóm platform integration | Chịu trách nhiệm token, logging, triển khai control. |
| **data_classification** | Internal / confidential / sensitive | Định mức tác động khi rò rỉ. |
| **access_scope** | Read-only event API; không có admin | Dùng để đánh giá đường tấn công. |
| **criticality** | High | Xác định ưu tiên và tần suất kiểm tra. |
| **service_dependencies** | checkout analytics; reporting | Biết tác động dây chuyền khi mất dịch vụ. |
| **subprocessors** | Cloud provider B, email provider C | Theo dõi fourth-party. |
| **contract/renewal** | Link hợp đồng, ngày gia hạn | Lịch cập nhật điều khoản và thoát hợp đồng. |
| **latest_assessment / next_review** | Ngày, kết luận, deadline | Ngăn tình trạng evidence hết hiệu lực. |
| **residual_risk / exceptions** | Medium; EXC-009 | Truy vết quyết định và owner. |
| **offboarding_status** | Active / retiring / terminated | Đảm bảo thu hồi quyền và xóa dữ liệu. |

Vendor inventory phải được đối chiếu với thực tế: danh sách thanh toán/mua sắm, SSO apps, OAuth grants, DNS/API keys, agent cài đặt, cloud marketplace và kho mã nguồn. Một “shadow SaaS” được người dùng tự đăng ký có thể không xuất hiện trong hệ thống mua sắm nhưng vẫn xử lý dữ liệu nhạy cảm.

### 3.2. Phân tầng theo tác động

Tầng đánh giá cần dựa trên **mức phơi nhiễm và hậu quả**, không chỉ giá trị hợp đồng.

| Tier minh họa | Tiêu chí | Mức assurance đề xuất |
|---|---|---|
| **Critical** | Nhà cung cấp nằm trên đường giao dịch thiết yếu, xử lý dữ liệu rất nhạy cảm hoặc có quyền kiểm soát hệ thống sản xuất quan trọng. | Thẩm định sâu, kiểm tra evidence theo phạm vi, đánh giá kiến trúc/điều khoản, scenario test, theo dõi thường xuyên. |
| **High** | Truy cập dữ liệu confidential, tích hợp rộng hoặc ảnh hưởng đáng kể tới hoạt động. | Đánh giá controls trọng yếu, chứng cứ độc lập và kiểm tra theo chu kỳ/trigger. |
| **Medium** | Quyền hạn giới hạn, dữ liệu ít nhạy cảm, có phương án thay thế. | Questionnaire tập trung và chứng cứ phù hợp, theo dõi thay đổi quan trọng. |
| **Low** | Không xử lý dữ liệu nhạy cảm, quyền truy cập thấp, có thể thay thế dễ. | Inventory, phê duyệt tối thiểu và xác minh những cam kết liên quan. |

Bảng trên chỉ là **ví dụ chính sách nội bộ**. Một vendor có hóa đơn nhỏ nhưng giữ service-account token có quyền sửa production có thể là rủi ro **Critical**. Tier cần được cập nhật nếu sản phẩm bổ sung AI feature, tăng quyền OAuth, thay nhà thầu phụ hoặc thu thập thêm dữ liệu.

## 4. Đánh giá inherent risk, kiểm soát và residual risk

### 4.1. Inherent risk là gì?

**Inherent risk** là mức rủi ro của hoạt động khi chưa xét đến hiệu quả của các controls giảm thiểu đang áp dụng. Nó giúp quyết định mức độ thẩm định cần thiết.

**Residual risk** là mức rủi ro còn lại sau khi đã tính đến các controls có bằng chứng hiệu lực, cùng các giới hạn của bằng chứng đó.

Không nên lấy số điểm tự khai của nhà cung cấp để trực tiếp quyết định residual risk: controls chưa được kiểm chứng hoặc chỉ áp dụng ngoài phạm vi sử dụng có thể không giảm được rủi ro thực tế.

### 4.2. Một phương pháp tính minh họa

Tổ chức có thể dùng thang **Likelihood (L)** và **Impact (I)** từ 1 đến 5, với ý nghĩa định nghĩa trước. Điểm ưu tiên **R = L × I** là một **heuristic xếp hạng**, không phải xác suất đo thực nghiệm hoặc mức tổn thất tiền tệ.

Ví dụ:

| Scenario | L (1–5) | I (1–5) | Inherent score | Controls và đánh giá |
|---|---:|---:|---:|---|
| API token vendor lộ và bị dùng để đọc dữ liệu nhạy cảm. | 4 | 5 | 20 | Scope read-only tối thiểu, rotation, logging và alert test. |
| Vendor bị gián đoạn 6 giờ làm ngừng reporting. | 3 | 3 | 9 | Queue/replay, cache nội bộ và phương án chuyển tạm. |
| Nhà thầu phụ truy cập dữ liệu sai mục đích. | 3 | 4 | 12 | Hạn chế dữ liệu gửi, phê duyệt subprocessor, hợp đồng và audit. |
| Thay đổi SDK gây lỗi tính toán ở ứng dụng. | 3 | 4 | 12 | Pin version/digest, code review, test và rollback. |

Sau kiểm chứng, owner có thể đánh giá giảm L hoặc I theo tiêu chí định sẵn; **không nên tự động trừ số điểm** chỉ vì vendor trả lời “Yes” trong questionnaire. Với rủi ro có tác động cao, trình bày cả **severity và evidence confidence**, không chỉ một số tổng hợp.

### 4.3. Risk register cần ghi những gì?

Một bản ghi rủi ro tối thiểu gồm:

- ID, vendor/service, asset và business process chịu ảnh hưởng.
- Threat scenario và **điều kiện xảy ra**, điểm tiếp xúc, trust boundary.
- Inherent likelihood/impact, lý do đánh giá và mức độ bất định.
- Controls phía vendor, controls phía khách hàng, evidence và hiệu lực.
- Residual risk, khả năng chấp nhận theo risk appetite, người có thẩm quyền.
- Gaps, remediation actions, owner, deadline, trigger tái đánh giá.
- Dữ liệu/hoạt động còn ngoài phạm vi evidence, ngoại lệ và ngày hết hạn.

Ví dụ một dòng rõ ràng: “VEN-014 có OAuth scope đọc tất cả customer records trong production dù chỉ cần sự kiện mua hàng đã loại PII. Inherent risk High; remediation là giảm scope và chuyển event sang proxy loại dữ liệu; chỉ hạ residual risk sau khi test quyền truy cập bị từ chối và xem log.”

## 5. Due diligence: đánh giá bằng chứng thay vì chỉ đánh giá câu trả lời

**Vendor due diligence** nên điều chỉnh theo tier, loại dữ liệu, quyền và threat model. Mục tiêu là xác định controls có hiệu lực cho **dịch vụ, pháp nhân, địa điểm và thời gian thực tế tổ chức sử dụng**.

### 5.1. Những nguồn evidence thường gặp

| Loại chứng cứ | Có thể giúp đánh giá | Không tự chứng minh |
|---|---|---|
| **Security questionnaire** | Vendor mô tả chính sách, controls, trách nhiệm, kiến trúc và quy trình. | Các controls được thực thi đúng trong mọi môi trường. |
| **SOC 2 Type 1 report** | Thiết kế controls tại một thời điểm theo phạm vi và tiêu chí của báo cáo. | Hiệu quả vận hành liên tục trong một khoảng thời gian dài. |
| **SOC 2 Type 2 report** | Kết quả kiểm toán thiết kế và hiệu quả vận hành controls trong kỳ đánh giá được nêu. | Toàn bộ sản phẩm, mọi subprocessor, mọi rủi ro ngoài phạm vi hoặc thời gian sau kỳ báo cáo. |
| **ISO/IEC 27001 certification** | ISMS được đánh giá/chứng nhận trong phạm vi và chu kỳ cụ thể. | Mọi dịch vụ/feature hoặc toàn bộ security controls kỹ thuật đều đã được kiểm thử. |
| **Penetration-test summary** | Kiểm thử một phạm vi kỹ thuật tại thời điểm và điều kiện xác định, với findings/khắc phục. | Không còn lỗ hổng; tính an toàn của các feature, tenant hoặc kỳ sau chưa test. |
| **Architecture/data-flow diagram** | Hiểu nơi lưu/truyền dữ liệu, boundaries, trust assumptions. | Cấu hình runtime hiện hành luôn khớp sơ đồ. |
| **Backup/DR exercise report** | Khả năng phục hồi đã được thử ở điều kiện ghi trong báo cáo. | Đạt mọi RTO/RPO khi xảy ra kịch bản khác hoặc tải lớn hơn. |
| **Incident / vulnerability process evidence** | Năng lực phát hiện, xử lý và thông báo có thực thi. | Một sự cố tương lai chắc chắn được phát hiện hoặc báo đúng hạn. |
| **Customer-side technical test** | Các quyền và đường tích hợp do khách hàng kiểm soát hoạt động đúng. | Controls nội bộ của vendor mà khách hàng không quan sát được. |
| **Independent audit / artifact attestation** | Xác nhận có giới hạn của bên kiểm tra độc lập về artifact/control. | Bảo đảm tuyệt đối hoặc phủ mọi thành phần. |

### 5.2. Đọc SOC 2 và chứng nhận đúng phạm vi

Khi xem một báo cáo assurance, cần kiểm tra:

1. **Legal entity, sản phẩm, hệ thống, địa điểm và kỳ đánh giá** có bao phủ đúng dịch vụ đang sử dụng không?
2. **Tiêu chí hoặc control objectives** nào được kiểm tra; có phù hợp confidentiality, availability, processing integrity, privacy hay risk scenario không?
3. **Ngoại lệ/findings** nào xuất hiện, vendor đã khắc phục ra sao và có bằng chứng retest không?
4. **CUECs (complementary user entity controls):** controls khách hàng phải tự thực hiện như MFA, phân quyền, cấu hình lưu trữ hoặc xét duyệt người dùng.
5. **Subservice organizations:** áp dụng cách tiếp cận carve-out hay inclusive theo báo cáo; kiểm soát của nhà thầu phụ có nằm ngoài phạm vi kiểm tra không?
6. **Ngày kết thúc kỳ báo cáo:** có bridge letter/updated evidence phù hợp cho khoảng thời gian còn trống không? Bridge letter là tuyên bố bổ sung, **không thay thế một cuộc kiểm toán mới**.
7. **Độ tin cậy và quyền sử dụng tài liệu:** xác minh nguồn, giới hạn phân phối, tính bảo mật và phạm vi điều khoản.

Với chứng nhận ISO/IEC 27001, cần xác định **phạm vi ISMS, tổ chức, địa điểm và hiệu lực chứng nhận**; không suy luận chứng nhận bao phủ mọi sản phẩm của tập đoàn. Có chứng nhận là thông tin hữu ích, nhưng vẫn phải nối với câu hỏi rủi ro, controls và bằng chứng của dịch vụ cụ thể.

### 5.3. Một questionnaire có cấu trúc

Câu hỏi cần cụ thể và kèm loại chứng cứ mong muốn:

| Miền | Câu hỏi | Bằng chứng kỳ vọng |
|---|---|---|
| **Governance** | Ai sở hữu security program, chính sách được rà soát khi nào? | Policy excerpt, trách nhiệm, phiên bản, review date. |
| **Access** | Production access của nhân viên/đối tác được cấp, ghi log, phê duyệt và thu hồi thế nào? | Access procedure, MFA/JIT model, access-review sample. |
| **Data protection** | Dữ liệu được mã hóa, phân vùng tenant và xóa theo lịch như thế nào? | Data flow, encryption/retention design, deletion process. |
| **Secure development** | Code review, dependency scanning, secret management và release approval được thực hiện ra sao? | SDLC policy, CI/CD control evidence hoặc independent assessment. |
| **Vulnerability management** | Phân loại lỗ hổng và thời hạn xử lý theo rủi ro thế nào? | Process, sampled remediation records, exception process. |
| **Logging & detection** | Ai giám sát IAM/production và phát hiện thay đổi logging? | Use-case list, log retention, monitoring test summary. |
| **Incident response** | Khi sự cố ảnh hưởng dữ liệu của khách hàng, ai quyết định, thông báo bằng cách nào và trong thời hạn nào? | IR plan, communication workflow, exercise results. |
| **BC/DR** | Dịch vụ thiết yếu có RTO/RPO nào và đã phục hồi thử trong điều kiện gì? | DR contract, dated exercise report, failures/remediation. |
| **Subprocessor** | Những bên nào tiếp cận dữ liệu hoặc hỗ trợ dịch vụ, cơ chế thay đổi thế nào? | Subprocessor register, processing scope, notice process. |
| **Exit** | Dữ liệu có thể export, quyền truy cập thu hồi và deletion chứng minh bằng gì? | Exit procedure, format, deletion confirmation mechanism. |

Câu trả lời “Yes” chỉ là **vendor assertion**. Với các rủi ro quan trọng, cần bằng chứng và đánh giá độ bao phủ. Nếu không thể chia sẻ raw audit vì bảo mật, có thể dùng báo cáo độc lập, redacted sample, walkthrough có giới hạn hoặc test phía khách hàng; ghi rõ **giới hạn assurance**.

## 6. Đo chất lượng của chứng cứ

Đánh giá evidence theo các chiều độc lập:

| Chiều | Câu hỏi | Ví dụ thiếu sót |
|---|---|---|
| **Relevance** | Chứng cứ liên quan đúng control và risk scenario? | Có policy password nhưng risk là API token bị lộ. |
| **Scope** | Bao phủ đúng dịch vụ, region, tenant, môi trường? | Báo cáo chỉ cho sản phẩm X, tổ chức dùng Y. |
| **Recency** | Bằng chứng có còn phù hợp với thời điểm hiện tại không? | Pentest đã cũ, nhiều feature mới chưa được xem xét. |
| **Independence** | Do vendor tự khai hay có đánh giá độc lập? | Toàn bộ evidence chỉ là self-attestation. |
| **Completeness** | Có điều kiện, exceptions, kết quả và mốc kiểm tra? | Bản tóm tắt bỏ các findings nghiêm trọng. |
| **Integrity/provenance** | Có biết nguồn, version, người cung cấp và có kiểm soát sửa đổi? | File nhận qua email không rõ kỳ/phiên bản. |
| **Testability** | Có thể gắn với kiểm thử, control của khách hàng và tiêu chí đạt? | Tài liệu marketing hứa “enterprise-grade security”. |

Không cộng điểm máy móc để thay thế phán đoán chuyên môn. Một chứng cứ độc lập có thể vẫn **không phù hợp phạm vi**, trong khi một test do khách hàng thực hiện có thể rất mạnh để xác nhận một control do chính khách hàng sở hữu.

### 6.1. Claim → control → evidence

~~~mermaid
flowchart LR
    R["Risk / threat scenario"] --> CLAIM["Security claim"]
    CLAIM --> CTRL["Vendor + customer controls"]
    CTRL --> TEST["Assessment / test"]
    TEST --> EVID["Evidence có phạm vi và thời điểm"]
    EVID --> DEC{"Kết luận"}
    DEC -->|Đạt| MON["Theo dõi thay đổi"]
    DEC -->|Chưa đạt| FIX["Finding / remediation / exception"]
    FIX --> TEST
    MON --> R
~~~

Ví dụ:

**Claim:** “Nhà cung cấp phân tích chỉ có thể đọc sự kiện mua hàng đã được phân loại cho phép, không thể đọc tài khoản thanh toán hoặc sửa đơn hàng.”

**Vendor control:** xử lý dữ liệu theo mục đích hợp đồng, phân tách tenant và giới hạn quyền nhân viên hỗ trợ.

**Customer control:** event proxy loại trường nhạy cảm, token read-only, allowlist nguồn, scoped credentials, logging và alert.

**Test:** so sánh schema đầu ra; dùng danh tính tích hợp thử gọi endpoint bị cấm và xác nhận bị từ chối; kiểm tra quyền OAuth, log truy cập, token rotation.

**Evidence:** kiến trúc, contract, export cấu hình token, test results, timestamps, reviewer decision. Chứng cứ này hỗ trợ claim trong **phạm vi token và đường tích hợp đã thử**, không chứng minh mọi quyền nội bộ của vendor.

## 7. Phân chia controls giữa nhà cung cấp và khách hàng

Nhà cung cấp có thể thực hiện security controls của mình, nhưng phía khách hàng vẫn cần điều khiển ranh giới sử dụng dịch vụ.

### 7.1. Shared responsibility minh họa

| Rủi ro/control | Vendor thường sở hữu | Customer thường sở hữu |
|---|---|---|
| Security của SaaS runtime | Harden platform, patching, tenant isolation, internal monitoring. | Cấu hình tenant, xác thực, quyền người dùng và API scopes. |
| Data protection | Mã hóa/lưu trữ theo dịch vụ, nhân viên hỗ trợ theo thỏa thuận. | Chọn dữ liệu chia sẻ, phân loại, dữ liệu tối thiểu, chính sách retention trong khả năng cấu hình. |
| Access management | Nhân viên/vendor admin privilege. | SSO/MFA, user provisioning, access review, token lifecycle. |
| Network/integration | API endpoint, bảo vệ dịch vụ đầu vào. | Egress allowlist, webhook verification, API gateway, traffic monitoring. |
| Incident response | Phát hiện, containment trong hệ thống vendor, thông báo theo thỏa thuận. | Đánh giá tác động, containment trong hệ thống mình, thông báo theo nghĩa vụ và phối hợp. |
| Backup/DR | DR của nền tảng dịch vụ theo phạm vi hợp đồng. | Data export/backup bổ sung nếu cần, chức năng degraded mode, exit planning. |
| Subprocessor | Lựa chọn, thẩm định, quản lý nhà thầu phụ. | Review/subprocessor change theo hợp đồng, đánh giá tác động dữ liệu. |

Trách nhiệm thực tế phụ thuộc **mô hình dịch vụ và hợp đồng**, không phải bảng trên là mặc định pháp lý. Ví dụ với IaaS, khách hàng thường sở hữu nhiều cấu hình OS, network và ứng dụng hơn so với SaaS.

### 7.2. Controls kỹ thuật ưu tiên

- **Least privilege:** chỉ cấp OAuth scopes, API role, VPN route, service account quyền tối thiểu; tách test/prod.
- **Strong authentication:** SSO/MFA cho người dùng, mTLS hoặc cơ chế xác thực hệ thống phù hợp; quản lý secret an toàn.
- **Short-lived access:** token/credential ngắn hạn hoặc rotation/thu hồi định kỳ theo khả năng nền tảng; dùng JIT cho hỗ trợ đặc quyền nếu có.
- **Data minimization:** gửi dữ liệu cần thiết, pseudonymization/redaction phù hợp, tránh đưa bí mật hay dữ liệu nhạy cảm vào analytics.
- **Segmentation:** tách mạng, tenant, egress, API gateway, allowlist và hạn chế các đường vận hành có thể vượt boundary.
- **Monitoring:** audit đăng nhập, grants, token usage, export, dữ liệu outbound và thay đổi cấu hình.
- **Resilience:** timeout, retry có backoff, circuit breaker, queue/dedup, graceful degradation và alternate provider khi BIA yêu cầu.
- **Supply-chain integrity:** pin artifact digest/version, provenance, signature/checksum khi có hỗ trợ, code review và kiểm tra cập nhật thư viện.
- **Revocation/exit:** xác minh có thể xóa tài khoản, revoke grants, chặn webhook và xóa dữ liệu trong phạm vi hợp đồng.

Một control “được cấu hình” phải được kiểm chứng ở trạng thái đang chạy. Ví dụ token đã được khai báo read-only nhưng test truy cập thực cho thấy vẫn sửa được đơn hàng thì kết luận cần ghi **FAIL**.

## 8. Hợp đồng và điều khoản bảo mật

Controls kỹ thuật không thể thay thế hoàn toàn quyền và nghĩa vụ được thiết lập trong hợp đồng. Với vendor quan trọng, cần hợp tác giữa business owner, procurement, legal/privacy, security và technical owner.

### 8.1. Các chủ đề hợp đồng thường cần xử lý

| Chủ đề | Điều cần mô tả | Bằng chứng vận hành liên quan |
|---|---|---|
| **Phạm vi dịch vụ/dữ liệu** | Mục đích, loại dữ liệu, chủ thể, hệ thống và quyền sử dụng. | Data flow, system inventory, data classification. |
| **Security baseline** | Yêu cầu quản lý truy cập, mã hóa, logging, phát triển an toàn, nhân sự hỗ trợ. | Chứng cứ control theo phạm vi. |
| **Incident notification** | Sự kiện nào phải thông báo, đầu mối, nội dung, phương thức và thời hạn được thống nhất. | Escalation test, contact list, incident exercise. |
| **Audit/assurance rights** | Quyền nhận báo cáo, làm rõ findings, đánh giá có giới hạn và xử lý ngoại lệ. | Assurance package, corrective action log. |
| **Subprocessors** | Công bố, kiểm soát thay đổi, nghĩa vụ ràng buộc tiếp và điều kiện phản hồi. | Subprocessor register, notices, review decisions. |
| **Data location/transfer** | Vị trí xử lý/lưu, điều kiện chuyển dữ liệu và yêu cầu áp dụng. | Region evidence, processor map, architecture. |
| **Retention/deletion** | Thời gian giữ, export format, backup deletion và cách xác nhận xóa theo lịch. | Deletion procedure, exit-test/deletion evidence. |
| **Availability/DR** | Service levels, phạm vi RTO/RPO khi phù hợp, dependencies và quy trình thông báo. | Status history, exercise report, outage response. |
| **Exit/transition support** | Thời gian hỗ trợ, data portability, phí và quyền truy cập sau chấm dứt. | Export test, migration/rollback plan. |
| **Change management** | Thông báo thay đổi lớn ảnh hưởng kiến trúc, quyền, dữ liệu hoặc vị trí xử lý. | Change notices, impact review. |

Thời hạn thông báo sự cố và nghĩa vụ xử lý dữ liệu **không có một con số cố định cho mọi bên**; phải đối chiếu loại dữ liệu, hợp đồng và quy định pháp luật thực tế áp dụng. Không sử dụng ví dụ đào tạo như tư vấn pháp lý.

### 8.2. Điều khoản không đủ nếu không thực thi

Một thỏa thuận “vendor sẽ thông báo nhanh khi có incident” rất khó kiểm toán nếu không định nghĩa **loại incident, trigger, kênh, đầu mối dự phòng, mốc thời gian và thông tin cần cung cấp**. Đối với dịch vụ quan trọng, thử liên lạc khẩn cấp và xác minh người trực có thể nhận, đánh giá và tiếp tục hoạt động.

Tương tự, điều khoản “xóa mọi dữ liệu khi kết thúc” cần xem **bao gồm bản sao backup hay không, thời hạn, ngoại lệ bắt buộc, cách xác nhận và khả năng thu hồi các tài khoản tích hợp**.

## 9. Fourth-party và concentration risk

### 9.1. Không thể quản lý rủi ro của vendor bằng tên vendor

Một SaaS có thể phụ thuộc cloud hosting, DNS, CDN, IdP, message delivery, analytics processor, nhà thầu hỗ trợ và nhiều thư viện. Những phụ thuộc này có thể tạo một **common-mode failure** khi nhiều vendor tưởng là độc lập lại dùng chung nhà cung cấp hạ tầng.

Ví dụ tổ chức sử dụng ba dịch vụ SaaS khác nhau nhưng cả ba đều đặt data plane cùng một region/cloud provider. Việc “đa dạng hóa vendor” chưa chắc giảm được rủi ro mất region.

Nên phân tích:

1. Vendor phụ thuộc trực tiếp những nhà thầu phụ nào cho dữ liệu và chức năng quan trọng?
2. Những bên nào có **quyền truy cập dữ liệu**, quyền quản trị hoặc khóa mã hóa?
3. Các bên này nằm ở quốc gia/region nào, retention và điều khoản thay đổi ra sao?
4. Có cùng IdP, cloud, DNS, KMS, payment rail hoặc network provider không?
5. Có alternative, failover, queue/replay, data portability hoặc degraded mode không?
6. Vendor có nghĩa vụ báo thay đổi trọng yếu và kiểm soát rủi ro của subprocessors không?

### 9.2. Fourth-party visibility có giới hạn

Khách hàng thường không có quyền audit trực tiếp mọi nth-party. Vì vậy có thể dùng một số lớp chứng cứ:

- Danh sách subprocessor và mô tả mục đích xử lý dữ liệu.
- Điều khoản vendor phải áp controls và nghĩa vụ bảo mật phù hợp cho subprocessor.
- Báo cáo độc lập mô tả hệ thống và cách đánh giá subservice organizations.
- Thử nghiệm resilience/phương án thay thế cho phụ thuộc trọng yếu.
- Cơ chế cảnh báo thay đổi nhà thầu phụ, thời điểm và cách khách hàng đánh giá tác động.

Nếu không có visibility cần thiết, ghi nhận **uncertainty** và rủi ro tồn dư, không tự suy “vendor đã audit subprocessor nên mọi thứ đạt”.

## 10. Từ onboarding đến giám sát liên tục

### 10.1. Vòng đời TPRM

~~~mermaid
flowchart LR
    A["Discover / Inventory"] --> B["Tier + Inherent risk"]
    B --> C["Due diligence + evidence review"]
    C --> D["Controls + contract + decision"]
    D --> E["Onboard / limited access"]
    E --> F["Monitor + reassess"]
    F --> G["Finding + remediation / exception"]
    G --> F
    F --> H["Renew / change / exit"]
    H --> I["Revoke, export, delete, verify"]
~~~

Mỗi bước cần có owner và tiêu chí đầu ra, đặc biệt với quan hệ High/Critical.

**Discovery:** vendor được tìm qua procurement, SSO, cloud, endpoint agent, API integrations và chi phí.

**Inherent risk:** xác định loại dữ liệu, quyền, mức quan trọng, fourth-party và kịch bản tấn công.

**Due diligence:** đối chiếu assertions với chứng cứ, ghi scope, hạn và gaps.

**Decision:** chấp thuận, chấp thuận có điều kiện, yêu cầu sửa trước onboard hoặc từ chối sử dụng theo thẩm quyền.

**Onboarding:** thực hiện cấu hình tích hợp, phân quyền, logging, hợp đồng và technical security validation.

**Monitoring:** theo dõi thay đổi quyền, incidents, risk signals, evidence expiry và sự kiện có thể làm thay đổi tier.

**Renewal/exit:** đánh giá lại khi gia hạn, thay chức năng, đổi dữ liệu hoặc chấm dứt; xác minh thu hồi quyền và dữ liệu.

### 10.2. Trigger tái đánh giá

Không nên chỉ đánh giá theo lịch hằng năm. Cần tái đánh giá khi có thay đổi đáng kể:

- Vendor xảy ra sự cố bảo mật hoặc gián đoạn có tác động.
- Vendor thêm subprocessor, đổi nơi lưu/xử lý dữ liệu hoặc sửa điều khoản.
- Sản phẩm có tính năng mới, đặc biệt là truy cập dữ liệu, AI processing, agent hoặc permission mới.
- Doanh nghiệp mở rộng scope dữ liệu, nhiều tenant hơn hoặc tăng quyền tích hợp.
- Chứng nhận, báo cáo SOC 2 hoặc pentest đã hết phạm vi thời gian phù hợp.
- Bên thứ ba bị mua lại, thay nhân sự quản trị, tổ chức hoặc thay chủ sở hữu dịch vụ.
- Contract renewal, thay đổi SLA/RTO/RPO hoặc kế hoạch exit.
- Kiểm toán phát hiện gap, control phía khách hàng bị đổi hoặc log/token usage bất thường.

### 10.3. Monitoring không chỉ là xem tin tức về vendor

Nên giám sát những tín hiệu trong **phạm vi tổ chức có thể quan sát và hành động**:

| Tín hiệu | Nguồn | Hành động |
|---|---|---|
| OAuth scope/service account được tăng quyền. | IdP/SSO, API gateway, IAM audit. | Review người phê duyệt, test least privilege, hạ quyền nếu sai. |
| Token của vendor dùng từ nguồn hoặc thời điểm bất thường. | API audit, proxy, service logs. | Triage, revoke/rotate khi có căn cứ, kiểm tra dữ liệu đã truy cập. |
| Lượng dữ liệu gửi tới SaaS tăng đột biến. | Egress/DLP, data pipeline metrics. | Xác định schema/PII, owner và change context. |
| Vendor incident/outage được thông báo. | Vendor status/notification chính thức, support ticket. | Kích hoạt impact assessment, IR/BC/DR khi cần. |
| Subprocessor hoặc region thay đổi. | Contract notice, vendor portal. | Data-impact review và quyết định tiếp tục sử dụng. |
| Báo cáo assurance hết kỳ/exception chưa sửa. | Evidence register, ticket. | Gọi review và yêu cầu cập nhật. |
| DR/exit test không đạt. | Runbook, exercise report. | Tạo finding, remediation và retest. |

Một điểm quan trọng: **mất tín hiệu không phải là không có rủi ro**. Nếu vendor ngừng gửi audit event hoặc API connector bị lỗi, phải có cảnh báo health/coverage thay vì coi việc không thấy sự kiện là an toàn.

## 11. Quản trị findings, ngoại lệ và residual risk

Một kết quả thẩm định có thể là **PASS / FAIL / INCONCLUSIVE / NOT ASSESSED / RISK ACCEPTED WITH CONDITIONS** tùy quy trình tổ chức. Các nhãn không nên bị dùng để che gaps.

### 11.1. Risk treatment

| Phương án | Khi phù hợp | Bằng chứng cần có |
|---|---|---|
| **Mitigate** | Có thể giảm rủi ro bằng control cụ thể. | Control plan, owner, deadline, kết quả test sau sửa. |
| **Avoid** | Rủi ro vượt khả năng chấp nhận và không thể giảm đủ. | Quyết định không onboard hoặc dừng tích hợp, kế hoạch ngừng dùng. |
| **Transfer/share** | Phân bổ một phần tổn thất hoặc trách nhiệm qua hợp đồng/bảo hiểm. | Điều khoản, giới hạn, chủ thể, nhưng vẫn cần controls kỹ thuật. |
| **Accept** | Rủi ro còn lại trong ngưỡng được người có thẩm quyền chấp thuận. | Risk acceptance record, lý do, ràng buộc, owner, thời hạn và trigger review. |

Chuyển giao tài chính không xóa bỏ rủi ro bảo mật dữ liệu và trách nhiệm với khách hàng. Chấp nhận rủi ro không biến control chưa triển khai thành “đạt”.

### 11.2. Mẫu finding có thể kiểm toán

~~~yaml
finding_id: TPR-2026-014
vendor_id: VEN-014
service: purchase-analytics
risk: "OAuth integration có quyền đọc dữ liệu khách hàng quá phạm vi"
inherent_rating: high
observed_condition:
  permission: "customers.read_all"
  required_permission: "purchase_events.read"
evidence:
  - "IAM-grants-snapshot-2026-11-28"
  - "integration-access-negative-test-01"
status: open
owner: platform-integration
remediation:
  - "Thay scope token, chuyển luồng qua event proxy giảm dữ liệu"
  - "Revoke token cũ và kiểm tra audit"
due_date: "2026-12-15"
verification:
  expected: "Không thể gọi API dữ liệu khách hàng bằng danh tính vendor"
  actual: "Chưa thực hiện retest"
risk_acceptance:
  approved: false
~~~

Đây là một **mẫu nội bộ**, không phải chuẩn YAML của một sản phẩm. Chỉ thay **status** thành closed sau khi đã xác minh control hiệu lực theo tiêu chí và có evidence phù hợp.

### 11.3. Ngoại lệ cần giới hạn

Nếu business owner cần dùng dịch vụ trước khi vendor khắc phục hoàn toàn, ngoại lệ chỉ nên được xem xét với:

- Phạm vi chức năng, dữ liệu, account và quyền được phép.
- Lý do nghiệp vụ, severity của rủi ro và lựa chọn thay thế đã đánh giá.
- Controls bù trừ; ví dụ giới hạn luồng dữ liệu, access proxy hoặc monitoring tăng cường.
- Người phê duyệt có thẩm quyền, ngày hết hạn và trigger kiểm tra lại.
- Quy tắc dừng quan hệ hoặc revoke token nếu điều kiện thay đổi.

Không tạo ngoại lệ vô hạn với nội dung “vendor đang cải thiện”. Nếu mức rủi ro quá cao so với risk appetite, quyết định phù hợp có thể là không triển khai.

## 12. Tình huống thực hành: SaaS phân tích giao dịch

### 12.1. Bối cảnh

Một công ty thương mại điện tử muốn gửi sự kiện mua hàng từ **order-api** sang một SaaS phân tích để đo conversion và retention. Vendor đề nghị cài SDK trong ứng dụng và cấp token OAuth để truy cập toàn bộ hồ sơ khách hàng. Nhà cung cấp báo có chứng nhận ISO/IEC 27001 và báo cáo SOC 2, nhưng phạm vi chứng cứ chưa được kiểm tra. Họ dùng một cloud provider và một công ty hỗ trợ dữ liệu là subprocessors.

**Mục tiêu kinh doanh:** có analytics gần thời gian thực; nếu SaaS không hoạt động, hệ thống checkout vẫn phải xử lý đơn bình thường.

**Mục tiêu bảo mật:** dữ liệu gửi tối thiểu, vendor không thể sửa đơn hay đọc dữ liệu thanh toán, truy cập và thay đổi quyền được giám sát, có khả năng tạm dừng tích hợp và xóa dữ liệu theo thỏa thuận.

### 12.2. Threat model và risk register sơ bộ

| Rủi ro | Inherent | Thiết kế giảm thiểu | Cần chứng minh |
|---|---|---|---|
| Vendor đọc PII vượt mục đích analytics. | High | Event proxy chỉ đẩy event cần thiết, pseudonymized ID, token scoped. | Data schema review, IAM snapshot, negative access tests. |
| SDK bị compromise và chạy trong checkout. | High | Tránh SDK chạy với quyền production không cần thiết; xử lý gửi event qua backend/proxy, pin artifact và review dependency. | Build provenance, dependency inventory, CI/test result. |
| Vendor outage gây lỗi checkout. | High | Async queue, timeout, circuit breaker, retry/backoff và dead-letter handling. | Failure-injection test, business transaction success. |
| Subprocessor truy cập dữ liệu ngoài dự tính. | Medium–High | Phạm vi xử lý, hợp đồng, notice, hạn chế loại dữ liệu từ nguồn. | Subprocessor register, data flow, agreement, change review. |
| Token bị lộ hoặc dùng sai mục đích. | High | Least privilege, vault, rotation, logging và revocation. | Scope snapshot, usage alert test, revoke test. |
| Không xóa được dữ liệu khi exit. | Medium–High | Export/delete plan, retention clauses, xóa quyền và backup lifecycle. | Offboarding exercise, deletion confirmation, access denial. |

Mức High chỉ là **đánh giá tình huống giả định**; trong thực tế cần xếp theo chính sách phân loại dữ liệu, tác động, threat và ngưỡng chấp nhận của tổ chức.

### 12.3. Đề xuất kiến trúc an toàn hơn

~~~mermaid
flowchart LR
    CUSTOMER["Khách hàng"] --> ORDER["Order API"]
    ORDER --> STORE["Order DB"]
    ORDER --> OUTBOX["Outbox / Event queue"]
    OUTBOX --> FILTER["Event proxy: allowlist & data minimization"]
    FILTER --> SAAS["Analytics SaaS"]
    SAAS --> SP["Subprocessors theo hợp đồng"]
    IAM["Scoped service identity + rotation"] --> FILTER
    OBS["Audit + DLP / egress monitoring"] --> FILTER
    OUTBOX --> RETRY["Retry / replay khi SaaS lỗi"]
~~~

Điểm thiết kế:

- Checkout không gọi SaaS đồng bộ trong đường giao dịch chính; event delivery dùng queue/outbox phù hợp.
- Event proxy chỉ chuyển các field đã phê duyệt, có schema validation; không dùng full customer object.
- Token có quyền gửi/đọc sự kiện theo API thực tế, không có quyền đọc thông tin thanh toán hay sửa đơn.
- Có timeout, retry có giới hạn, idempotency, dead-letter handling và phương án xử lý backlog theo retention.
- Monitoring ghi nhận token usage, event volume, lỗi export và thay đổi cấu hình/permissions.
- Có phương án dừng gửi dữ liệu, revoke, export và delete theo nhu cầu exit.

### 12.4. Kiểm thử tối thiểu

| Test ID | Thiết lập/thao tác | Tiêu chí chấp nhận | Evidence |
|---|---|---|---|
| **T01 Data minimization** | Tạo event mua hàng giả có các trường nhạy cảm và chạy qua proxy. | Dữ liệu gửi vendor không chứa field ngoài allowlist; hành vi lỗi schema bị xử lý đúng. | Event trước/sau redaction, parser/schema version. |
| **T02 Least privilege** | Dùng danh tính tích hợp thử gọi API sửa đơn hoặc đọc dữ liệu thanh toán. | Request bị từ chối; quyền hiện hành đúng scope. | API response, IAM/OAuth grants snapshot, audit event. |
| **T03 Availability** | Mô phỏng SaaS timeout/trả lỗi trong lab. | Checkout vẫn hoàn tất, queue giữ event trong giới hạn và có cảnh báo backlog. | Test timeline, order IDs, queue/error metrics. |
| **T04 Credential lifecycle** | Rotate/revoke test credential theo quy trình. | Token cũ mất quyền, token mới hoạt động đúng, không rò secret vào log. | Rotation record, API deny/allow results. |
| **T05 Monitoring** | Phát yêu cầu trái phép hoặc anomalous test traffic theo phạm vi được phép. | Alert tới đúng owner với actor, context và runbook. | Raw audit, rule version, alert/case timeline. |
| **T06 Fourth-party** | Đối chiếu danh sách subprocessors và data flow. | Mỗi bên truy cập dữ liệu trong scope được biết, gaps có owner. | Register, contract notice, review signoff. |
| **T07 Exit drill** | Xuất dữ liệu mẫu, xóa tài khoản test và revoke integration. | Có thể chuyển dữ liệu theo format cam kết; quyền sau revoke bị từ chối; deletion record có giới hạn rõ. | Export/restore test, access tests, exit checklist. |

Khi làm test, chỉ dùng hệ thống/tài khoản và dữ liệu đã được ủy quyền. Không thử xâm nhập vào hạ tầng nội bộ của vendor nếu hợp đồng và phạm vi cho phép chưa rõ. Các phép kiểm tra từ phía khách hàng rất có giá trị, nhưng không chứng minh mọi control bên trong SaaS.

### 12.5. Xem xét SOC 2 và ISO của vendor trong tình huống

Giả sử báo cáo SOC 2 bao phủ **nền tảng analytics SaaS** trong kỳ đã công bố, nhưng chức năng AI mới được triển khai sau kỳ báo cáo. Khi đó:

- Có thể sử dụng báo cáo để đánh giá **các controls trong kỳ và phạm vi nêu rõ**.
- Không suy ra feature AI mới được bao phủ; cần tài liệu bổ sung về dữ liệu đầu vào, retention, subprocessors, quyền nhân viên và validation.
- Cần xem exceptions, CUECs và phạm vi subservice organizations.
- Chứng nhận ISO/IEC 27001 có giá trị đối với ISMS trong scope; không thay thế test quyền OAuth ở phía khách hàng.

**Kết luận assurance phù hợp:** có thể chấp thuận onboarding có điều kiện nếu dữ liệu/permissions được giới hạn và các test critical pass; mọi gap trọng yếu chưa đủ chứng cứ phải có owner, điều kiện chấp thuận, thời hạn và quyết định theo risk appetite.

## 13. Offboarding và exit risk

Một tổ chức dễ bỏ qua rủi ro khi **kết thúc hợp đồng**: token còn hiệu lực, dữ liệu vẫn được giữ, subprocessor chưa được thông báo, webhook vẫn bắn dữ liệu hoặc khóa mã hóa chưa được xử lý theo chính sách.

### 13.1. Exit checklist

1. Chốt **business owner**, ngày dừng, phạm vi dữ liệu, account và hệ thống phụ thuộc.
2. Xác nhận bản export sử dụng được, định dạng/metadata đầy đủ, khả năng di chuyển sang dịch vụ khác.
3. Cắt luồng dữ liệu mới; vô hiệu webhook, agent, OAuth grants, VPN, SSO app và service principals.
4. Rotate các secrets/keys có thể đã được vendor biết hoặc chia sẻ.
5. Kiểm tra không còn account hoạt động, privilege, API connection hoặc network route không cần thiết.
6. Yêu cầu xóa hoặc giữ dữ liệu theo nghĩa vụ hợp lệ, bao gồm phạm vi backup/subprocessor và thời gian hoàn tất.
7. Nhận confirmation/evidence từ vendor về deletion/retention theo khả năng xác minh.
8. Đối chiếu logs và giám sát nếu có hoạt động sau thời điểm offboarding.
9. Cập nhật inventory, risk register, contract status và ngày kết thúc retention/evidence.
10. Giữ hồ sơ audit, exceptions và bài học để cải thiện quy trình lựa chọn vendor lần sau.

Khi chưa thể chứng minh xóa hoàn toàn dữ liệu, ghi rõ giới hạn xác nhận (ví dụ vendor xác nhận quy trình xóa theo lịch backup) và rủi ro tồn dư, thay vì tuyên bố “đã xóa hết” không có cơ sở.

## 14. Đo hiệu quả chương trình third-party assurance

Các KPI cần phản ánh khả năng quản lý rủi ro, không chỉ số questionnaire đã gửi.

| Chỉ số | Cách tính hoặc định nghĩa | Giới hạn |
|---|---|---|
| **Inventory coverage** | Số quan hệ vendor trong scope đã có owner, dữ liệu, quyền và tier / tổng quan hệ phát hiện được. | Mẫu số bị sai nếu còn shadow SaaS chưa phát hiện. |
| **Critical vendor assessment coverage** | Số vendor Critical có đánh giá phù hợp và evidence hiện hành / tổng vendor Critical. | Đánh giá “có” chưa chắc chất lượng evidence tốt. |
| **High-risk finding closure rate** | Finding High được xác minh khắc phục / tổng finding High đến hạn, theo định nghĩa kỳ báo cáo. | Không tính closed khi chỉ có cam kết sửa. |
| **Evidence freshness** | Tỷ lệ evidence trọng yếu còn hiệu lực theo policy và thời điểm. | Chứng cứ mới nhưng ngoài phạm vi vẫn không hữu ích. |
| **Exemption aging** | Tuổi/độ quá hạn của ngoại lệ, phân nhóm theo severity và owner. | Cần phân biệt gia hạn được phê duyệt với quá hạn. |
| **Access exposure** | Số integration còn quyền rộng, tài khoản vendor không dùng, token lâu không rotate hoặc không có owner. | Phải đặt tiêu chí theo công nghệ và mức rủi ro. |
| **Response readiness** | Tỷ lệ vendor Critical có đầu mối incident, kênh thông báo và diễn tập/kiểm chứng phù hợp. | Hợp đồng chỉ ghi số điện thoại chưa chứng minh khả năng nhận và xử lý. |
| **Exit readiness** | Tỷ lệ dịch vụ quan trọng có data export/revocation test gần đây. | Kiến trúc thay đổi có thể làm kết quả cũ hết hiệu lực. |
| **Concentration exposure** | Tỷ lệ dịch vụ thiết yếu phụ thuộc một provider/region/subprocessor theo mô hình failure domain. | Phải nhìn phụ thuộc thực, không chỉ số vendor trên giấy. |
| **Third-party incident impact** | Sự cố bên thứ ba và thời gian/chi phí/tác động theo phân loại. | Có thể bị thiếu do vendor thông báo trễ hoặc không đầy đủ. |

Không suy ra “rủi ro giảm” chỉ vì tổng số báo cáo SOC 2 tăng. Một chương trình assurance trưởng thành thể hiện rõ **gaps nào được đóng, controls nào đã được kiểm chứng, độ tin cậy của dữ liệu và điều kiện rủi ro đã thay đổi ra sao**.

### 14.1. Đặt lịch rà soát theo rủi ro

Ví dụ chính sách nội bộ:

- Vendor Critical: review định kỳ dày hơn, monitoring và escalation rõ ràng, kiểm tra lại sau incident/đổi dữ liệu/quyền.
- Vendor High: rà soát có chu kỳ và theo sự kiện thay đổi quan trọng.
- Vendor Medium/Low: đánh giá tối thiểu theo mức phơi nhiễm, nhưng vẫn có owner và trigger tái đánh giá.

Không có một tần suất duy nhất đúng cho mọi ngành. Việc xác định chu kỳ phải gắn với **risk appetite, cam kết hợp đồng, yêu cầu áp dụng và khả năng thay đổi**.

## 15. Mẫu assurance package cho một quan hệ bên thứ ba

~~~text
assurance/third-party/VEN-014/
  vendor-profile.md
  service-inventory-and-data-flow.md
  business-impact-and-tier.md
  risk-register.csv
  diligence/
    questionnaire-answers.md
    evidence-index.csv
    soc2-scope-and-exceptions-review.md
    iso-certification-scope-review.md
    architecture-and-security-review.md
    subprocessor-list-review.md
  agreements/
    security-requirements.md
    incident-notification-and-contacts.md
    data-processing-and-exit-terms.md
  technical-validation/
    iam-oauth-scope-snapshot.json
    network-and-data-minimization-tests.json
    monitoring-validation.json
    resilience-and-exit-drill.md
  findings/
    remediation-plan.csv
    exceptions-and-approvals.md
    retest-results.json
  review/
    decision-and-residual-risk.md
    next-review-and-change-triggers.md
~~~

Đây là **cách sắp xếp minh họa**, không phải yêu cầu đặt tên file chuẩn. Các tài liệu kiểm toán độc lập và hợp đồng có thể bị giới hạn quyền sử dụng/phân phối; cần lưu an toàn, tránh sao chép nội dung nhạy cảm vào hệ thống không được cấp phép.

Một **evidence record** nên có: vendor ID, control ID, claim, asset/data scope, phương pháp kiểm tra, source, kỳ hiệu lực, phiên bản, người cung cấp, ngày review, exceptions, kết luận, người chịu trách nhiệm và liên kết đến finding hoặc retest. Trường hợp thiếu evidence phải ghi là **unknown/not verified**, không coi như PASS.

## 16. Sai lầm thường gặp

1. **“Có ISO/SOC 2 nên toàn bộ vendor an toàn.”** Báo cáo có scope, kỳ và exceptions; có thể không bao phủ sản phẩm, feature hoặc subprocessor đang dùng.
2. **“Vendor trả lời Yes nên control đã hoạt động.”** Self-attestation cần đối chiếu evidence hoặc test theo rủi ro.
3. **“Rủi ro đã chuyển hết sang cloud/SaaS.”** Customer vẫn có trách nhiệm về dữ liệu, quyền, tích hợp và residual risk theo mô hình dịch vụ.
4. **“Hợp đồng nhỏ nên risk thấp.”** Vendor có quyền production hoặc xử lý dữ liệu rất nhạy cảm có thể gây tác động lớn dù chi phí thấp.
5. **“Third-party inventory chỉ cần danh sách nhà cung cấp thanh toán.”** OAuth app, browser extension, agent, SDK và SaaS tự đăng ký có thể tạo shadow dependencies.
6. **“Fourth-party nằm ngoài hợp đồng nên không cần xem.”** Họ có thể quyết định nơi dữ liệu được xử lý và tính sẵn sàng của dịch vụ.
7. **“Vendor có backup nên outage không ảnh hưởng mình.”** Hệ thống khách hàng vẫn cần queue, degraded mode, runbook, data portability và test.
8. **“Chấm dứt hợp đồng là xong quyền truy cập.”** Token, VPN, SSO, webhook, service account và dữ liệu lưu vẫn cần thu hồi/xác nhận.
9. **“Không có tin xấu về vendor nghĩa là control tốt.”** Không có thông tin không chứng minh không có sự cố, cần monitoring và evidence coverage.
10. **“Risk accepted đồng nghĩa đã khắc phục.”** Chấp nhận rủi ro cần người có thẩm quyền, phạm vi, thời hạn và trigger xem xét lại.
11. **“Đánh giá xong một lần dùng mãi.”** Dữ liệu, quyền, feature, kiến trúc, nhân sự và nhà thầu phụ thay đổi theo thời gian.
12. **“Hạ điểm residual risk khi đã gửi remediation plan.”** Phải xác minh control hoạt động hoặc ghi rõ rủi ro chưa khắc phục.

## 17. Bài tập tình huống

Một doanh nghiệp dùng ba nhà cung cấp: **Vendor A** xử lý email marketing; **Vendor B** cung cấp payment API; **Vendor C** cung cấp dịch vụ giám sát production có quyền đọc log tập trung. Tất cả đều có chứng nhận; A dùng dữ liệu email và hành vi khách hàng, B xử lý giao dịch tài chính, C đọc log có thể chứa secret và định danh khách hàng. Cả ba cùng sử dụng một cloud provider ở một region.

**Yêu cầu:**

1. Xác định tài sản, dữ liệu, quyền và kịch bản rủi ro trọng yếu cho A, B, C. Vì sao chứng nhận không đủ để xếp tier?
2. Thiết kế inventory có vendor ID, business/technical owner, nơi lưu dữ liệu, quyền truy cập, tier và các fourth parties.
3. Phân loại inherent risk theo Likelihood × Impact có lý do, nêu bất định và tiêu chí residual risk.
4. Chỉ rõ ít nhất hai controls phía **khách hàng** và hai controls phía **vendor** cho mỗi quan hệ.
5. Viết ba claim có thể kiểm chứng; mỗi claim có một phép thử, một artifact evidence và tiêu chí PASS.
6. Xác định concentration risk của việc cả ba dùng cùng cloud region và một phương án giảm phụ thuộc.
7. Lập một kịch bản sự cố: Vendor C bị lộ tài khoản hỗ trợ. Bạn cần revoke quyền nào, truy log gì, liên lạc ai và tìm evidence gì?
8. Mô tả cách offboard Vendor A: ngừng data flow, thu hồi token, export dữ liệu cần thiết, yêu cầu xác nhận xóa và cập nhật risk register.

**Gợi ý:** Vendor C có thể là High/Critical dù chỉ “đọc log” nếu log chứa secrets có thể tái sử dụng hoặc thông tin điều tra quan trọng. Không tự suy rằng mọi dữ liệu log đều vô hại. Vendor B có mức phụ thuộc sẵn sàng rất cao; cần xem cả resilience và các nghĩa vụ bảo vệ dữ liệu/định danh.

## 18. Checklist Third-party assurance có thể kiểm toán

- [ ] Có third-party inventory được đối chiếu với procurement, SSO, API, agent, cloud và SaaS usage.
- [ ] Mỗi quan hệ có business owner, technical owner, dịch vụ, dữ liệu, quyền và phụ thuộc được mô tả.
- [ ] Xác định tier theo data sensitivity, quyền, criticality và concentration, với tiêu chí nhất quán.
- [ ] Threat scenarios và ranh giới tin cậy được viết cụ thể.
- [ ] Inherent risk có lập luận; residual risk chỉ giảm khi controls có evidence phù hợp.
- [ ] Đánh giá evidence về relevance, scope, recency, independence, completeness và provenance.
- [ ] Đọc đúng phạm vi/kỳ/exceptions/CUECs/subservice của SOC 2 và phạm vi ISMS của ISO/IEC 27001 nếu sử dụng.
- [ ] Có mapping rõ vendor controls và customer controls, kèm owner.
- [ ] Tích hợp có quyền tối thiểu, credential lifecycle, segmentation, data minimization và logging/monitoring.
- [ ] Contract nêu phạm vi dữ liệu, security requirements, incident communication, subprocessor, retention, audit và exit theo rủi ro.
- [ ] Có chương trình giám sát thay đổi, evidence expiry, incident notice, privileged access và telemetry health.
- [ ] Fourth-party và concentration risk được đánh giá trong phạm vi visibility thực tế.
- [ ] Backup/DR, resilience, data portability và offboarding được thử ở mức phù hợp criticality.
- [ ] Findings có severity, owner, deadline và retest; exceptions có phê duyệt, điều kiện và hết hạn.
- [ ] Mọi claim có test/evidence, phạm vi và timestamp; không đánh dấu PASS dựa trên assertion đơn lẻ.
- [ ] Khi gia hạn, thêm quyền, thêm dữ liệu, xảy ra sự cố hoặc đổi subprocessor có trigger đánh giá lại.
- [ ] Chấm dứt quan hệ có bằng chứng revoke, export, dừng luồng dữ liệu và xử lý retention/deletion.
- [ ] Reviewer độc lập truy vết được **risk → control → evidence → decision → remaining risk**.

## 19. Câu hỏi tự đánh giá

1. Khi nào một nhà cung cấp có chi phí thấp vẫn phải được xếp Critical?
2. Vì sao SOC 2 Type 2 có giá trị hơn self-assessment cho một số controls nhưng vẫn không chứng minh toàn bộ dịch vụ an toàn?
3. Một báo cáo kiểm toán kết thúc trước khi vendor ra mắt tính năng AI mới có bao phủ tính năng đó không? Cần evidence bổ sung gì?
4. Inherent risk và residual risk khác nhau thế nào? Khi nào có thể hạ điểm rủi ro tồn dư?
5. “Hai vendor khác nhau” có đủ chứng minh giảm concentration risk không nếu họ cùng dùng một cloud region?
6. Làm thế nào phân biệt trách nhiệm vendor và trách nhiệm khách hàng đối với OAuth token, SSO và dữ liệu gửi vào SaaS?
7. Một tài khoản vendor bị thu hồi nhưng vẫn còn webhook đang nhận dữ liệu; offboarding đã đạt chưa?
8. Vì sao test quyền truy cập bị từ chối bằng token vendor có thể là bằng chứng mạnh hơn việc questionnaire khẳng định least privilege?
9. Nếu vendor không cho xem raw audit vì lý do bảo mật, những cách nào có thể giảm uncertainty và giới hạn nào vẫn phải ghi?
10. Hãy thiết kế một monitoring trigger và một phép diễn tập để chứng minh tổ chức có thể ứng phó khi nhà cung cấp quan trọng gặp sự cố.

**Điểm cốt lõi:** Third-party risk xuất hiện từ **sự phụ thuộc bên ngoài và quyền/dữ liệu đi qua ranh giới tin cậy**. Một chương trình third-party assurance hiệu quả phải biết mình phụ thuộc ai, kịch bản nào có thể gây thiệt hại, controls nào thuộc mỗi bên, bằng chứng nào thực sự bao phủ rủi ro và cách kiểm chứng trong vận hành. Kết luận cần dựa trên scope, thời điểm, test, findings và residual risk, tiếp tục được rà soát suốt vòng đời hợp tác.

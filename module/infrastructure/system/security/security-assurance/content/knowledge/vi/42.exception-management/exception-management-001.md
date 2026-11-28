# Security exception: Quản lý ngoại lệ bảo mật có điều kiện, có thời hạn và có bằng chứng

Một ứng dụng cũ vẫn cần phục vụ khách hàng nhưng chưa hỗ trợ cách xác thực quản trị theo chính sách mới. Nhóm vận hành đề nghị “ngoại lệ bảo mật sáu tháng” và cam kết sẽ nâng cấp sau. Nếu người quản lý chỉ bấm **Approve**, liệu hệ thống đã an toàn hơn? Nếu đến hạn không có bản nâng cấp, quyền truy cập đã mở rộng, còn biện pháp bù trừ chưa từng được kiểm thử, thì chữ ký phê duyệt có thể trở thành cách hợp thức hóa rủi ro kéo dài thay vì kiểm soát rủi ro.

**Security exception** (ngoại lệ bảo mật) là **quyết định có kiểm soát cho phép một đối tượng cụ thể tạm thời hoặc theo điều kiện được xác định không tuân theo một yêu cầu, security standard, baseline hay control nội bộ**, khi cơ chế quản trị cho phép. Quyết định đó phải nêu rõ phạm vi, lý do, rủi ro, người chịu trách nhiệm, biện pháp giảm thiểu, thời hạn, cách theo dõi và điều kiện kết thúc. **Security exception không đồng nghĩa hệ thống đạt control gốc, và càng không mặc nhiên miễn nghĩa vụ pháp luật hoặc hợp đồng**.

Bài học thuộc chương **Exception management** của module **SECURITY_SECURITY_ASSURANCE**. Module hướng tới việc xây dựng đánh giá **có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật từ rủi ro, yêu cầu và security controls đến kiểm thử, audit, khắc phục finding và assurance liên tục. Vì thế, quản lý security exception không chỉ là một mẫu đơn hành chính: nó tạo **đường truy vết từ khoảng lệch kỹ thuật đến quyết định quản trị rủi ro và trạng thái thực tế của control** trong phát triển và vận hành.

Sau bài học, người học có thể nhận diện và phân loại security exception, xác định khi nào được phép xin ngoại lệ, thiết kế hồ sơ và workflow phê duyệt, đánh giá compensating controls, quản lý expiry và sự thay đổi phạm vi, tách risk acceptance khỏi kết luận control, thu thập bằng chứng audit và đóng ngoại lệ dựa trên kết quả retest.

## 1. Security exception giải quyết vấn đề gì?

Trong hệ thống thực, việc áp dụng ngay mọi baseline bảo mật có thể gặp hạn chế: sản phẩm legacy, thiết bị không thể dừng, dependency bên thứ ba, thay đổi kiến trúc phức tạp hoặc rủi ro phát sinh khi triển khai gấp. Một chương trình security assurance cần hai khả năng đồng thời:

1. **Bảo vệ tính bắt buộc của yêu cầu:** tình trạng chưa đáp ứng phải được nhận diện trung thực; không cho phép tự ý bỏ qua.
2. **Quản trị những trường hợp có thể được phép lệch:** giảm rủi ro trong thời gian giới hạn, phân quyền quyết định và đặt lộ trình khắc phục kiểm chứng được.

Nếu không có cơ chế ngoại lệ, đội vận hành có thể tạo “ngoại lệ ngầm” bằng cách tắt rule, gắn nhãn false positive, trì hoãn scan hoặc giữ hệ thống ngoài inventory. Nếu cho phép ngoại lệ tùy tiện, chính sách mất hiệu lực và báo cáo tuân thủ trở nên thiếu tin cậy.

### 1.1. Security exception phải giúp trả lời sáu câu hỏi

| Câu hỏi | Thông tin bắt buộc |
|---|---|
| **Lệch khỏi yêu cầu nào?** | Control/standard ID, phiên bản, tiêu chí, nguồn yêu cầu. |
| **Đối tượng nào bị ảnh hưởng?** | Asset IDs, identity, dịch vụ, environment, region, loại dữ liệu, thời kỳ. |
| **Vì sao không sửa ngay?** | Nguyên nhân kỹ thuật/nghiệp vụ, lựa chọn đã xem xét và phụ thuộc. |
| **Rủi ro còn lại là gì?** | Threat scenario, exposure, impact, likelihood, kiểm soát hiện có. |
| **Ai có quyền quyết định và giám sát?** | Requestor, control owner, risk owner, người review và phê duyệt. |
| **Ngoại lệ kết thúc bằng cách nào?** | Expiry, milestones, mitigation, retest, điều kiện thu hồi và closure. |

Một request thiếu một trong các nhóm căn bản không nên được tự động phê duyệt chỉ vì “cần gấp để release”.

## 2. Phân biệt exception, deviation, finding và risk acceptance

Các thuật ngữ liên quan có thể xuất hiện trong cùng một vụ việc nhưng đóng vai trò khác nhau.

| Khái niệm | Nội dung chính | Có tự làm control gốc PASS không? |
|---|---|---|
| **Security requirement/control** | Điều kiện hệ thống hoặc quy trình phải đáp ứng theo phạm vi. | Không áp dụng; là chuẩn đối chiếu. |
| **Deviation/nonconformity** | Trạng thái thực tế lệch khỏi yêu cầu, dù có được cho phép hay không. | Không. |
| **Finding** | Phát hiện đã được đánh giá kèm bằng chứng, tác động và đối tượng liên quan. | Không; mô tả sự thiếu hụt/rủi ro. |
| **Security exception** | Quyết định cho phép lệch **theo cơ chế áp dụng**, có ràng buộc. | Không. Chỉ xác định điều kiện được phép tiếp tục. |
| **Waiver/dispensation** | Một dạng miễn/cho phép theo chính sách hoặc chương trình cụ thể. | Chỉ có ý nghĩa theo quy tắc của nguồn yêu cầu; không đồng nhất mọi nơi. |
| **Risk acceptance** | Người có thẩm quyền chấp nhận rủi ro còn lại trong một giới hạn cụ thể. | Không; rủi ro được chấp nhận không đồng nghĩa control hoạt động. |
| **Compensating control** | Biện pháp bổ sung/thay thế để giảm rủi ro khi control gốc thiếu. | Phải test; có thể không được chuẩn/hợp đồng công nhận tương đương. |
| **Temporary mitigation** | Giảm phơi nhiễm khi chờ sửa triệt để. | Không; không chứng minh root cause được xử lý. |
| **Remediation action plan** | Kế hoạch sửa lỗi, owner, dependency, deadline và verification. | Chỉ kết luận khi sửa và retest đạt. |
| **False positive / N/A** | Phát hiện sai hoặc yêu cầu thực sự không áp dụng có căn cứ. | Phải xác minh; không dùng như tên khác của exception. |

### 2.1. Một ví dụ nhiều trạng thái cùng tồn tại

Chính sách kỹ thuật yêu cầu tất cả node production phải dùng một phiên bản TLS tối thiểu. Một endpoint legacy chưa đáp ứng.

- **Control result:** FAIL với endpoint đó theo tiêu chí đã ban hành.
- **Exception request:** đang chờ hoặc đã được quyết định theo thẩm quyền.
- **Mitigation:** giới hạn nguồn kết nối, chặn giao thức yếu ở lớp proxy nếu phù hợp kiến trúc.
- **Compensating control result:** chỉ PASS khi có test thực tế.
- **Risk decision:** ACCEPTED_WITH_CONDITIONS tới ngày được phê duyệt, nếu đúng quyền.
- **Remediation:** nâng cấp endpoint và thử lại TLS policy.
- **External compliance:** phải đánh giá riêng nếu có hợp đồng/luật/quy định buộc phải dùng cấu hình đó.

Đánh dấu **`compliant: true`** cho toàn bộ trường hợp chỉ vì có chữ ký acceptance là cách báo cáo sai bản chất.

## 3. Ranh giới: Yêu cầu nào có thể xin ngoại lệ?

Không được giả định mọi security requirement đều nằm trong quyền “miễn” của một trưởng nhóm kỹ thuật.

### 3.1. Xác định nguồn yêu cầu

| Nguồn | Ví dụ | Kiểm tra trước khi xử lý |
|---|---|---|
| **Chính sách nội bộ** | MFA, least privilege, tần suất access review. | Chủ chính sách, đối tượng áp dụng, cơ chế ngoại lệ và thẩm quyền. |
| **Security standard/baseline nội bộ** | Mã hóa, logging, secure configuration, patch SLA. | Standard version, quan hệ với policy cấp trên, điều kiện thay thế. |
| **Kiến trúc/SDLC gate** | Code review, test bảo mật trước release, secret scanning. | Có quyền bypass theo điều kiện nào và ai có quyền quyết định? |
| **Hợp đồng/SLA/DPA** | Cam kết audit log, thời hạn lưu, xử lý dữ liệu, subprocessor. | Cần sửa hợp đồng hoặc chấp thuận của bên có quyền không? |
| **Luật và quy định** | Nghĩa vụ bảo vệ dữ liệu hoặc an toàn ngành. | Có cơ chế miễn trừ hợp pháp không; ai có thẩm quyền? |
| **Chương trình chứng nhận/đánh giá** | Bộ tiêu chí một chương trình bên ngoài yêu cầu. | Quy tắc xử lý không phù hợp, phương án bù trừ, yêu cầu báo cáo. |

Một **security exception nội bộ** có thể cho phép vận hành có điều kiện khi lệch một chuẩn nội bộ. Nhưng nếu cùng tình trạng cũng vi phạm cam kết hợp đồng hoặc một yêu cầu pháp lý bắt buộc, hồ sơ nội bộ **không tự xóa bỏ trách nhiệm**. Cần phân tách kết luận kỹ thuật, quyết định rủi ro và tính hợp lệ theo nguồn nghĩa vụ.

### 3.2. Quy tắc “đủ thẩm quyền”

Trước khi tạo nhánh phê duyệt, xác minh: văn bản nào cho phép ngoại lệ, ai có quyền, rủi ro tối đa nào được chấp nhận, cần bên liên quan nào được tham vấn và liệu có phải xin sự chấp thuận/điều chỉnh từ bên ngoài hay không.

Nếu chưa xác nhận applicability, trạng thái phù hợp là **PENDING_APPLICABILITY_REVIEW** hoặc tương đương. Không coi việc không trả lời email là đồng ý, trừ khi chính cơ chế hợp đồng/luật áp dụng quy định cụ thể và điều kiện ấy đã được xác minh.

### 3.3. Security exception không dành để che lỗi inventory

Một asset không có trong danh mục hoặc một account không được scanner đọc không nhất thiết đã được ngoại lệ. Phải phân biệt **thiếu coverage evidence** với **control không đạt**; xử lý evidence gap và scope trước khi ra quyết định cho phép lệch.

## 4. Những tình huống Security exception thường gặp

| Trường hợp | Khoảng lệch | Rủi ro chính | Ví dụ hướng xử lý có điều kiện |
|---|---|---|---|
| **Ứng dụng legacy thiếu MFA trực tiếp** | Không đáp ứng yêu cầu xác thực quản trị theo tiêu chí cụ thể. | Credential theft, bypass qua đường quản trị. | Bastion/JIT có MFA, chặn direct path, session audit, kế hoạch thay ứng dụng. |
| **Không thể vá máy chủ đúng kỳ** | Patch SLA vượt hạn. | Lỗ hổng bị khai thác trong thời gian chờ. | Segmentation, giảm dịch vụ phơi lộ, EDR/virtual patching, test và lịch bảo trì. |
| **Thiết bị OT/IoT không hỗ trợ agent** | Thiếu endpoint telemetry theo baseline. | Mất detection/response, điểm xâm nhập khó quan sát. | Network monitoring, allowlist, vendor controls, thay thiết bị. |
| **Encryption chưa đồng nhất** | Một số dữ liệu/volume chưa áp dụng yêu cầu. | Đọc trái phép dữ liệu hoặc backup. | Giới hạn quyền, mã hóa ở lớp khác đã kiểm thử, thiết kế migration. |
| **Một SaaS không cung cấp audit log cần thiết** | Không đáp ứng control observability. | Không thể điều tra hoặc chứng minh truy cập. | Log thay thế, hợp đồng hỗ trợ, giới hạn use case, đánh giá vendor. |
| **Release gấp chưa đủ kiểm thử** | Chưa đạt secure release gate. | Vulnerabilities vào production. | Feature flag, staged rollout, test tối thiểu, approval và retest deadline. |
| **Lỗ hổng không có patch từ vendor** | Không đạt remediation time objective. | Exploitability kéo dài. | Chặn attack path, giảm exposure, theo dõi advisory và phương án thay. |
| **Hệ thống hết hỗ trợ (EOL)** | Không thể duy trì patch và support. | Lỗ hổng không có bản sửa, dependency lỗi thời. | Cô lập, hạn sử dụng, hỗ trợ đặc biệt nếu có, migration/decommission. |
| **Break-glass incident** | Cần quyền cao hoặc bypass workflow thông thường. | Lạm dụng đặc quyền và thiếu trách nhiệm. | Quy trình khẩn cấp, logging, giới hạn TTL, kiểm tra sau và thu hồi quyền. |

**Lưu ý:** danh sách biện pháp là gợi ý để đánh giá, **không phải bằng chứng chúng tương đương hoặc bảo đảm đủ an toàn**. Cần test theo kiến trúc thực và kiểm tra điều kiện cho phép của nguồn yêu cầu.

## 5. Vòng đời quản lý Security exception

Quy trình nên khép kín từ phát hiện tới khi bỏ được nguyên nhân hoặc có quyết định xử lý khác phù hợp.

~~~mermaid
flowchart TD
    A["Phát hiện deviation / yêu cầu ngoại lệ"] --> B["Xác định requirement, scope và evidence"]
    B --> C{"Có cơ chế cho phép ngoại lệ?"}
    C -->|Không| D["Xử lý noncompliance, thay thiết kế hoặc xin chấp thuận đúng thẩm quyền"]
    C -->|Có| E["Threat/risk assessment và lựa chọn xử lý"]
    E --> F["Thiết kế và test compensating controls"]
    F --> G{"Bằng chứng + residual risk đủ để xem xét?"}
    G -->|Không| H["Bổ sung test, giảm phạm vi hoặc từ chối"]
    H --> E
    G -->|Có| I["Approval có điều kiện, owner, TTL, action plan"]
    I --> J["Triển khai, monitor, review định kỳ"]
    J --> K{"Expiry / incident / scope drift / mitigation lỗi?"}
    K -->|Có| L["Reassess, revoke hoặc renewal có kiểm soát"]
    L --> E
    K -->|Không| M["Remediation + retest control gốc"]
    M --> N{"Closure criteria đạt?"}
    N -->|Không| E
    N -->|Có| O["Đóng ngoại lệ, thu hồi quyền tạm và giữ evidence"]
~~~

### 5.1. Các điểm kiểm soát cần có

- **Gate 1 — Applicability:** yêu cầu gốc có thực sự áp dụng và được phép có ngoại lệ không?
- **Gate 2 — Risk:** threat scenario và residual risk có được đánh giá theo phương pháp phê duyệt?
- **Gate 3 — Mitigation:** biện pháp tạm đã có evidence về hiệu lực, không chỉ proposal?
- **Gate 4 — Authorization:** người quyết định có đúng quyền, có điều kiện và thời hạn?
- **Gate 5 — Operation:** scope và điều kiện được theo dõi trong thời gian còn hiệu lực?
- **Gate 6 — Exit:** control gốc đã retest, hoặc rủi ro được xử lý bằng phương án khác được phép, lịch sử được bảo toàn?

Trạng thái ngoại lệ phải cho biết **đang ở gate nào**, không dùng “Approved” để thay kết luận hiệu lực kỹ thuật.

## 6. Thiết kế hồ sơ yêu cầu ngoại lệ (Exception request)

Một biểu mẫu tốt nên có đủ dữ liệu để reviewer ra quyết định, không buộc người đánh giá lần theo nhiều cuộc trao đổi rời rạc.

| Nhóm thông tin | Những trường cần lưu |
|---|---|
| **Identity** | Exception ID, phiên bản, người đề nghị, ngày tạo, trạng thái. |
| **Requirement** | Control ID, source document/version, điều kiện lệch, policy owner. |
| **Scope** | Service, asset/account IDs, identity, môi trường, region, dữ liệu, use case, entry points. |
| **Rationale** | Lý do chưa đáp ứng, root cause, giới hạn công nghệ, phương án đã thử. |
| **Risk** | Asset criticality, threat actors, attack paths, impact, likelihood/exposure, inherent/residual risk. |
| **Control hiện có** | Baseline liên quan, logging, IAM, segmentation, backup và dependency. |
| **Compensating measures** | Thiết kế, người triển khai, phạm vi, test method, evidence, limitation. |
| **Approvals** | Người review kỹ thuật, compliance/legal khi cần, risk owner có quyền, decision và timestamp. |
| **Time** | Effective from, expires at, review cadence, remediation milestones, sự kiện thu hồi. |
| **Remediation** | Finding/action plan IDs, owner, dependency, deadline, acceptance criteria, retest. |
| **Monitoring** | Sources, thresholds, incidents và cách báo sự cố của control bù trừ. |
| **Evidence & governance** | Link đến raw/test evidence, phân quyền kho, retention và lịch sử quyết định. |

### 6.1. Scope phải có thể máy kiểm tra

“Cho phép ngoại lệ trên môi trường legacy” là quá rộng. Tốt hơn: “Chỉ hai máy chủ **asset-201/asset-202**, hai ứng dụng quản trị có định danh rõ, trong **production account X**, chỉ với **human admin** đã đăng ký, qua **bastion Y**, từ ngày A đến ngày B.” Không tự động áp dụng cho máy thứ ba hoặc đường kết nối support mới.

### 6.2. Phân biệt request và approved exception

Một request mới nộp là **PENDING**, chưa cho phép vận hành khác baseline. Nếu cần xử lý khẩn, phải đi theo **emergency authorization path** đã thiết kế; không tự gắn ngày phê duyệt hồi tố chỉ vì hệ thống đã chạy ngoài chính sách.

### 6.3. Liên kết issue và action plan

Mỗi security exception nên liên kết ít nhất một finding hoặc documented control deviation, cùng kế hoạch xử lý. Nếu một exception áp dụng cho nhiều asset, danh mục phải có IDs; nếu một asset có nhiều control gap khác nhau, chúng có thể cần nhiều quyết định/risk assessment thay vì một “waiver tổng” thiếu phạm vi.

## 7. Đánh giá rủi ro trước khi phê duyệt

Phê duyệt ngoại lệ là một quyết định **chịu rủi ro có thông tin**, không phải biểu quyết theo mức khó khăn kỹ thuật. Security assessor phải xây dựng **threat scenario có khả năng xảy ra** và chứng minh controls tạm thời tác động thế nào.

### 7.1. Các câu hỏi đánh giá

1. **Asset/value:** Tài sản nào, dữ liệu gì, ai có thể bị ảnh hưởng và tính thiết yếu tới nghiệp vụ?
2. **Threat:** Ai có thể khai thác control gap, bằng thông tin/quyền gì, có dấu hiệu đang khai thác không?
3. **Exposure:** Internet-facing hay private? Có đường bên thứ ba, VPN, identity liên kết, session hoặc token riêng?
4. **Vulnerability:** Yếu điểm thuộc cấu hình, thiết kế, phần mềm, vận hành hay quy trình?
5. **Impact:** Mất bí mật, toàn vẹn, khả dụng, quyền riêng tư, an toàn vật lý hoặc nghĩa vụ bên ngoài?
6. **Existing controls:** Những control nào thực sự hoạt động và đã được kiểm thử?
7. **Compensating controls:** Phòng ngừa, hạn chế đặc quyền, phát hiện, phản ứng hay giảm hậu quả ở mức nào?
8. **Duration:** Rủi ro tăng như thế nào nếu tình trạng kéo dài hoặc threat landscape thay đổi?
9. **Risk appetite:** Ai có thẩm quyền phê duyệt residual risk và trong điều kiện nào?
10. **Alternatives:** Có thể tắt feature, đổi thiết kế, giảm dữ liệu, cô lập hoặc thay nhà cung cấp thay vì ngoại lệ không?

### 7.2. Inherent risk và residual risk

- **Inherent risk:** mức rủi ro theo phương pháp tổ chức khi chưa tính những biện pháp giảm thiểu liên quan đang được đánh giá.
- **Residual risk:** mức còn lại sau khi đã xét những biện pháp được **triển khai và kiểm chứng đủ phù hợp**.

Chỉ vì dự kiến triển khai bastion không có nghĩa residual risk đã giảm. Nếu chưa thực thi hoặc chưa có bằng chứng, đánh giá nên ghi **planned mitigation**, chưa coi là control đang hoạt động.

### 7.3. Đừng dùng CVSS làm câu trả lời duy nhất

CVSS hoặc severity từ scanner hỗ trợ phân loại vulnerability, nhưng việc quyết định ngoại lệ còn cần exposure thực tế, tính quan trọng, khả năng khai thác, threat intelligence, thời gian chờ, kiểm soát bù trừ và nghĩa vụ. Cũng không được hạ severity vô căn cứ để exception đi qua luồng phê duyệt nhẹ hơn.

### 7.4. Một ma trận quyết định minh họa

| Điều kiện rủi ro | Hướng xử lý |
|---|---|
| Có khai thác đang diễn ra, dữ liệu trọng yếu phơi lộ hoặc nghĩa vụ không cho phép ngoại lệ | Ưu tiên containment/remediation, tham vấn đúng thẩm quyền; không dùng approval nội bộ để bỏ qua. |
| Rủi ro cao nhưng có biện pháp giảm hiệu lực, scope hẹp và deadline thực tế | Chỉ xem xét ở cấp thẩm quyền phù hợp, monitor chặt và có trigger thu hồi. |
| Rủi ro trung bình, controls thay thế có test và kế hoạch sửa rõ | Có thể chấp thuận có điều kiện theo chính sách, kỳ hạn và chủ sở hữu. |
| Rủi ro thấp trong scope xác định, control gap không ảnh hưởng mục tiêu trọng yếu | Workflow đơn giản hơn nếu được policy cho phép, vẫn cần evidence và expiry. |
| Không đủ dữ liệu xác minh rủi ro hoặc source obligation | **INCONCLUSIVE / PENDING REVIEW**; bổ sung bằng chứng trước quyết định. |

Đây là mô hình minh họa, không phải ma trận rủi ro chuẩn cho mọi tổ chức.

## 8. Compensating controls: Thay thế có điều kiện, không phải phép miễn trừ

Một **compensating control** phải tác động tới **mục tiêu rủi ro** của yêu cầu đang thiếu, có thể đo hiệu lực và nằm trong quyền được công nhận. Biện pháp phát hiện không nhất thiết tương đương biện pháp phòng ngừa; một proxy chặn đường truy cập chỉ hữu ích nếu không còn đường bypass khác.

### 8.1. Ví dụ ứng dụng legacy thiếu MFA native

| Biện pháp | Rủi ro giảm | Bằng chứng cần có | Giới hạn |
|---|---|---|---|
| **MFA tại bastion/JIT gateway** | Hạn chế đăng nhập bằng mật khẩu lộ từ đường quản trị đã định. | Effective policy, thử đăng nhập, danh sách users và exceptions. | Không bảo vệ direct console/SSH hoặc token path nằm ngoài bastion. |
| **Chặn đường quản trị trực tiếp** | Giảm bypass MFA. | Network policy, firewall rules, thử denied connections từ nhiều đường. | Asset mới hoặc config drift có thể tạo đường khác. |
| **Least privilege và session TTL** | Giảm impact và thời gian lạm dụng đặc quyền. | Role mapping, access review, session expiration test. | Credential hijack vẫn có thể gây thiệt hại trong cửa sổ còn quyền. |
| **Privileged session logging + alert** | Phát hiện và hỗ trợ điều tra. | Synthetic audit event, ingest tại SIEM, trang bị alert on-call. | Detection không tự ngăn hành động trước khi alert được xử lý. |
| **Segmentation/allowlist** | Thu hẹp mạng có thể tiếp cận service. | Reachability test, network inventory, thay đổi policy được audit. | Một máy nguồn được cho phép vẫn có thể bị xâm nhập. |
| **Migration có mốc** | Loại bỏ giới hạn legacy trong tương lai. | Milestone, thiết kế, budget, test và deployment. | Lộ trình chưa triển khai không giảm ngay residual risk. |

Nếu policy nói “mọi **đường quản trị** phải có MFA”, bastion có MFA và loại bỏ direct path có thể đáp ứng mục tiêu theo kiến trúc mới; cần đánh giá lại cách định nghĩa control gốc, không máy móc coi thiếu MFA native luôn là FAIL. Nếu policy yêu cầu MFA **tại ứng dụng** hoặc một yêu cầu bên ngoài định nghĩa cụ thể hơn, phải ghi rõ sự khác biệt và kiểm tra quyền sử dụng biện pháp thay thế.

### 8.2. Thiết kế kiểm thử control bù trừ

Mỗi control bù trừ nên có:

- **Claim:** điều kiện bảo vệ gì được khẳng định.
- **Test scope:** các assets/identities/entry points và thời gian được kiểm tra.
- **Positive test:** đường hợp lệ vẫn hoạt động.
- **Negative test:** hành vi không được phép bị từ chối hoặc cảnh báo.
- **Evidence:** raw logs, effective policies, config, test run, người chạy.
- **Review:** ai xác minh, kết luận và phần chưa kiểm.
- **Drift trigger:** điều gì khiến kết quả test cũ không còn đại diện.

Không kết luận “biện pháp bù trừ hiệu quả” chỉ vì một task đã được đóng hoặc ảnh chụp màn hình có trạng thái *enabled*.

## 9. Thẩm quyền phê duyệt và phân tách trách nhiệm

Người đề nghị ngoại lệ thường có áp lực hoàn thành công việc; người chấp nhận rủi ro phải có khả năng nhìn nhận tác động rộng hơn. Vì vậy cần **RACI/segregation of duties** tương xứng mức rủi ro.

| Vai trò | Trách nhiệm minh họa |
|---|---|
| **Requestor / System Owner** | Nêu lý do, scope, tài sản, phương án, thời hạn và cung cấp evidence. |
| **Control Owner** | Giải thích mục tiêu yêu cầu, phạm vi áp dụng và cách đo control. |
| **Security Assessor** | Kiểm tra technical gap, threats, compensating controls, residual risk và chất lượng evidence. |
| **Risk/Business Owner** | Quyết định chấp nhận rủi ro trong hạn mức được ủy quyền và chịu trách nhiệm hậu quả. |
| **Legal/Compliance/Privacy** | Đánh giá quyền cho phép ngoại lệ, nghĩa vụ pháp luật/hợp đồng, nghĩa vụ thông báo. |
| **Engineering/Operations** | Triển khai bảo vệ tạm, thực hiện remediation, đo và giám sát. |
| **Independent Assurance/Audit** | Thẩm định quy trình, bằng chứng và kết luận; không thay vai trò risk owner. |
| **Governance Committee** | Xem trường hợp vượt hạn mức, xung đột thẩm quyền, rủi ro kéo dài khi cơ chế có quy định. |

### 9.1. Ví dụ ma trận quyền

- **Mức thấp:** control owner + business/service owner có thể duyệt nếu chính sách quy định.
- **Mức trung bình:** security/risk review độc lập trước khi business owner quyết định.
- **Mức cao:** cấp có quyền cao hơn, điều kiện giám sát chặt và thời hạn ngắn hơn theo chính sách.
- **Liên quan nghĩa vụ bên ngoài:** legal/compliance đánh giá riêng; có thể phải xin sửa/chấp thuận theo hợp đồng hoặc không thể cho phép.

Đây là ví dụ mô hình tổ chức, **không phải quy định chuẩn**. Không cho một cá nhân vừa bỏ control, vừa tự đánh giá và tự duyệt, rồi tự ký retest đối với đối tượng có rủi ro đáng kể.

### 9.2. Bản ghi phê duyệt có thể truy vết

Một record “Approved by Security” chưa đủ nếu thiếu danh tính, quyền được ủy quyền, nội dung được duyệt, version đánh giá, điều kiện, thời gian hiệu lực và decision log. Khi người phê duyệt rời tổ chức, quyết định còn hiệu lực hay cần chuyển ownership phải được quy định trong quy trình.

## 10. State machine và quy tắc chuyển trạng thái

Security exception nên có state machine rõ để tránh “Approved” là trạng thái vĩnh viễn.

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> SUBMITTED
    SUBMITTED --> UNDER_REVIEW
    UNDER_REVIEW --> NEEDS_INFO
    NEEDS_INFO --> UNDER_REVIEW
    UNDER_REVIEW --> REJECTED
    UNDER_REVIEW --> APPROVED
    APPROVED --> ACTIVE: điều kiện kích hoạt đạt
    APPROVED --> REVOKED: điều kiện chưa đạt
    ACTIVE --> REASSESSING: thay đổi rủi ro / renewal
    REASSESSING --> ACTIVE: approval mới, phạm vi được xác minh
    REASSESSING --> REVOKED
    ACTIVE --> EXPIRED: đến hạn
    ACTIVE --> REVOKED: vi phạm điều kiện
    ACTIVE --> CLOSURE_REVIEW: remediation đã triển khai
    CLOSURE_REVIEW --> CLOSED: retest đạt
    CLOSURE_REVIEW --> ACTIVE: retest chưa đạt và còn quyền hợp lệ
    EXPIRED --> REASSESSING: đề nghị mới, không tự active
    REJECTED --> [*]
    REVOKED --> [*]
    CLOSED --> [*]
~~~

### 10.1. Ý nghĩa các trạng thái quan trọng

| Trạng thái | Điều kiện | Quyền tiếp tục lệch khỏi baseline? |
|---|---|---|
| **DRAFT/SUBMITTED** | Hồ sơ chưa được đánh giá. | Không mặc định có quyền. |
| **UNDER_REVIEW/NEEDS_INFO** | Đang xác minh yêu cầu, rủi ro và evidence. | Không mặc định có quyền. |
| **APPROVED** | Có quyết định nhưng có thể chưa đủ điều kiện kích hoạt. | Chỉ theo điều kiện quyết định. |
| **ACTIVE** | Đúng scope, đúng thời hạn, biện pháp bắt buộc đạt và quyền còn hiệu lực. | Có, trong giới hạn đã duyệt. |
| **REASSESSING** | Có trigger thay đổi hoặc xin gia hạn. | Phụ thuộc quyết định hiện hành; không suy ra được gia hạn. |
| **EXPIRED** | Qua hạn mà không có quyết định gia hạn hợp lệ. | Không còn được xem là ngoại lệ đang được cho phép. |
| **REVOKED/REJECTED** | Bị từ chối hoặc thu hồi. | Không. Cần risk treatment phù hợp. |
| **CLOSURE_REVIEW** | Đã triển khai sửa, đang kiểm tra. | Nếu exception hết hạn, vẫn cần xử lý riêng; không tự kéo dài. |
| **CLOSED** | Có bằng chứng và quyết định kết thúc đúng cơ chế. | Không cần tiếp tục ngoại lệ đó; policy áp dụng theo trạng thái mới. |

### 10.2. Không cho phép trạng thái làm mờ hiện thực

Ví dụ exception vẫn *ACTIVE* trong GRC, nhưng một API gateway mới mở đường bypass. **Trạng thái dữ liệu** không chứng minh điều kiện vẫn đúng. Hệ thống giám sát cần phát hiện drift và kích hoạt reassessment/containment. Một quyết định đã từng hợp lệ có thể **không còn phù hợp** sau thay đổi kiến trúc hoặc threat.

## 11. Thời hạn, gia hạn, hết hạn và thu hồi

Một ngoại lệ không có ngày hết hiệu lực dễ trở thành baseline ngầm. Mặc dù một số trường hợp đặc biệt có thể cần thời gian dài hoặc tái thẩm định theo chu kỳ, **ngày review và điều kiện hiệu lực phải rõ** theo quy trình được duyệt.

### 11.1. Ba mốc thời gian riêng

- **Effective from:** khi quyết định được phép áp dụng.
- **Review by / next assessment:** khi phải đánh giá lại rủi ro, scope và control bù trừ.
- **Expires at:** thời điểm ngoại lệ hết hiệu lực nếu không được duyệt lại.

Thêm **permanent remediation target** để theo dõi thời gian xử lý nguyên nhân. Ngày gia hạn ngoại lệ không tự kéo ngày remediation; cả hai cần approval và lý do riêng.

### 11.2. Điều kiện gia hạn hợp lệ

Một lần renewal nên yêu cầu:

1. Bằng chứng về tình trạng control gốc và phạm vi tại thời điểm hiện tại.
2. Lý do vì sao remediation chưa hoàn tất, đã làm gì so với milestones trước.
3. Risk assessment mới: exposure, threats, incidents, data, thay đổi môi trường.
4. Kiểm thử hiện hành của compensating controls và các giới hạn.
5. Xem lựa chọn giảm thêm scope, dừng chức năng, chuyển vendor hoặc đầu tư nguồn lực.
6. Quyết định của đúng thẩm quyền; hạn mới, trigger và lịch kiểm tra.
7. Bảo toàn **original due date** và lịch sử các lần gia hạn.

Không tự động đổi ngày trong record để tránh báo cáo overdue. Nếu một ngoại lệ hết hạn rồi mới được phê duyệt lại, cần đánh giá **khoảng thời gian không được cho phép**, không gộp thành hiệu lực liên tục.

### 11.3. Thu hồi trước hạn

Một security exception có thể phải được thu hồi hoặc giới hạn khi:

- Có tấn công thực tế liên quan control gap.
- Biện pháp bù trừ không hoạt động.
- Thêm asset, identity, data category hoặc region vượt scope.
- Thay đổi cách xử lý dữ liệu tạo nghĩa vụ mới.
- Nhận threat intelligence cho biết đường khai thác đã khả thi.
- Vendor mất hỗ trợ, log không còn hoặc dependency thay đổi.
- Người có thẩm quyền xác định residual risk vượt mức đã chấp nhận.

**Thu hồi không phải cứ lập tức tắt dịch vụ bằng mọi giá**: hành động kỹ thuật cần do incident/change authority chọn theo tác động, bảo vệ dữ liệu và kế hoạch an toàn. Nhưng hệ thống không được tiếp tục báo “exception active and compliant” khi điều kiện đã sai.

## 12. Giám sát Security exception trong vận hành

Sau phê duyệt là giai đoạn rủi ro tồn tại lâu nhất. Chương trình assurance cần kiểm tra **hiệu lực liên tục**, không chỉ chữ ký tại ngày bắt đầu.

| Nguồn tín hiệu | Cần theo dõi | Hành động khi sai |
|---|---|---|
| **Asset/identity inventory** | Server mới, tài khoản mới hoặc role mới trong đường được ngoại lệ. | Kiểm tra scope; không mặc định tài sản mới được miễn. |
| **Effective security configuration** | MFA, firewall, encryption, policy/guardrail, patch status. | So với điều kiện; cảnh báo owner và reassess. |
| **Threat/vulnerability feed** | Exploit xuất hiện, CVE mới, cảnh báo từ vendor. | Đổi risk rating và mitigation khi cần. |
| **SIEM/EDR/SOAR** | Lỗi control bù trừ, truy cập đặc quyền, alert bất thường. | Triage, IR/containment, evidence và review. |
| **Change/CI/CD** | Deploy, schema, API endpoint, network route thay đổi. | Tái kiểm tra bypass paths và acceptance criteria. |
| **Vendor/service status** | Chứng nhận/báo cáo cũ, API log thay đổi, hợp đồng hoặc support bị ngừng. | Yêu cầu evidence và phương án thay thế. |
| **Action plan** | Milestone, blocker, deadline, retest status. | Escalation, replan có quyền và cập nhật residual risk. |
| **Expiry scheduler** | Review dates, risk owner còn hiệu lực, pending renewal. | Nhắc hạn, cờ overdue, không auto-approve. |

### 12.1. Kiểm tra “monitoring thật sự hoạt động”

Một dashboard có rule alert chưa chắc dữ liệu đi hết pipeline. Hãy thử synthetic event phù hợp (trên phạm vi được phép), xác minh từ nguồn tới SIEM/ticket và người trực. Nếu ngoại lệ phụ thuộc vào cảnh báo hoạt động, **mất logging hoặc routing phải là trigger** xem lại quyền tiếp tục vận hành.

### 12.2. Review có phân biệt scope và rủi ro

Một ngoại lệ cho endpoint nội bộ có thể trở nên nghiêm trọng khi endpoint được mở Internet. Cần sự kiện phát hiện tự động hoặc review kiến trúc giúp nhận ra; không chỉ nhìn “đã duyệt tới cuối quý” rồi bỏ qua thay đổi thực tế.

## 13. Security exception và khắc phục: Không để remediation đứng yên

Ngoại lệ được cho phép nhằm xử lý một khoảng lệch có giới hạn; không thay thế kế hoạch sửa nguyên nhân.

### 13.1. Lộ trình hai đường

~~~text
Phát hiện control gap
  ├─ Đường A: Interim risk reduction
  │    ├─ Bảo vệ tạm và kiểm thử
  │    ├─ Monitor hiệu lực, incidents, drift
  │    └─ Reassess khi hết hạn/thay đổi
  │
  └─ Đường B: Permanent remediation
       ├─ Root-cause analysis
       ├─ Thiết kế/triển khai fix qua change management
       ├─ Test bảo mật và nghiệp vụ
       └─ Independent retest + closure decision
~~~

### 13.2. Tiêu chí đóng không phải “đã merge PR”

Đối với ứng dụng legacy thiếu MFA, một bản cập nhật code đã merge và deploy chưa chứng minh mọi đường quản trị có MFA. Cần kiểm tra effective enforcement, break-glass, đường trực tiếp, tài khoản nhà thầu và các phiên hiện có theo scope. Sau khi retest thành công mới có cơ sở đóng control gap.

### 13.3. Những cách kết thúc khác ngoài “fixed”

| Outcome | Khi nào hợp lý | Điều phải chứng minh |
|---|---|---|
| **FIXED_AND_VERIFIED** | Root cause đã được sửa và control gốc đạt. | Test đúng phạm vi, environment và thời điểm. |
| **RISK_REMOVED_BY_DECOMMISSION** | Tài sản/luồng xử lý thực sự được loại bỏ. | Tắt truy cập, revoke secrets, xử lý dữ liệu/dependencies, không còn đường khai thác. |
| **REPLACED_BY_APPROVED_DESIGN** | Thiết kế khác đáp ứng mục tiêu và được thừa nhận theo nguồn yêu cầu. | Design review, điều kiện hợp lệ, test end-to-end. |
| **RISK_ACCEPTED_WITH_SEPARATE_GOVERNANCE** | Một số rủi ro còn được chấp nhận theo thẩm quyền. | Hồ sơ acceptance còn hạn và trạng thái control được báo đúng; không gọi fixed. |
| **CLOSED_AS_FALSE_POSITIVE** | Phát hiện ban đầu được chứng minh sai. | Evidence và reviewer phân tích lại nguồn; không dùng để né repair. |

## 14. Evidence chain và kết luận Security Assurance

Một hồ sơ ngoại lệ đáng tin phải cho phép auditor lần ngược từ **quyết định → rủi ro → kiểm soát bù trừ → bằng chứng → control gốc → hành động khắc phục và kết luận**.

~~~mermaid
flowchart TD
    R["Requirement/version + scope"] --> O["Observed gap / original test result"]
    O --> F["Finding + evidence source"]
    F --> Q["Exception request + risk assessment"]
    Q --> C["Compensating control design"]
    C --> E["Implementation, test, evidence IDs"]
    E --> A["Risk owner approval + conditions + TTL"]
    A --> M["Monitoring/review/expiry evidence"]
    M --> X["Remediation and production change"]
    X --> T["Retest original control"]
    T --> Z["Closure decision + historical audit trail"]
~~~

### 14.1. Tối thiểu phải lưu gì?

| Artifact | Chứng minh điều gì? | Giới hạn |
|---|---|---|
| **Original finding/test** | Control gap nào được quan sát, trên tài sản nào. | Có thể chỉ là point-in-time hoặc sample. |
| **Applicability/authority record** | Quy trình cho phép ngoại lệ và quyền quyết định. | Không chứng minh kỹ thuật đạt. |
| **Risk assessment** | Kịch bản rủi ro và căn cứ lựa chọn. | Phụ thuộc dữ liệu, scope và giả định tại thời điểm. |
| **Compensating control tests** | Những biện pháp thay thế nào thực sự vận hành. | Có thể không bao phủ mọi bypass path. |
| **Approval decision** | Ai quyết định điều gì, trong hạn và điều kiện nào. | Không tự xóa noncompliance kỹ thuật. |
| **Monitoring review logs** | Điều kiện được theo dõi trong kỳ hiệu lực. | Thiếu telemetry làm suy giảm tin cậy. |
| **Remediation/change record** | Cái gì đã được thay trong code/cấu hình/kiến trúc. | Triển khai thành công chưa bằng retest PASS. |
| **Retest/closure evidence** | Kết quả control gốc và lý do đóng. | Cần đúng environment, asset và kỳ. |

### 14.2. Nguồn gốc, toàn vẹn và dữ liệu nhạy cảm

Một evidence record tốt có source system, resource ID, timestamp UTC, người hoặc collector, phương pháp, phiên bản, scope, artifact ID, các phép biến đổi và kết quả reviewer. Hash/versioning hoặc kho chống sửa có thể hỗ trợ tính toàn vẹn; **hash không chứng minh dữ liệu nguồn đã đầy đủ hay đúng trước khi băm**.

Security exception có thể phơi lộ chi tiết lỗi, sơ đồ mạng, tài khoản đặc quyền hoặc thông tin cá nhân. Phải lưu tài liệu ở kho **need-to-know**, phân quyền, retention theo chính sách, redaction khi báo cáo và ghi audit của việc truy cập. Không đưa mật khẩu, token, nội dung secret hoặc exploit payload nhạy cảm không cần thiết vào ticket công khai.

### 14.3. Evidence gap vs control failure

Nếu scanner không đọc được một máy chủ, đó là **thiếu bằng chứng** để khẳng định máy chủ đã vá hay chưa, không nhất thiết là máy chủ chưa vá. Nếu endpoint trả về giao thức yếu được xác nhận bằng test hợp lệ, đó là **control failure**. Action plan và kết quả assurance cần phân loại khác nhau, tránh làm méo dữ liệu rủi ro.

## 15. Tách các trục PASS/FAIL/INCONCLUSIVE

Một ngoại lệ không chỉ có một boolean. Cần đo ít nhất bốn trục:

| Trục đánh giá | Câu hỏi | Ví dụ kết quả |
|---|---|---|
| **Original control effectiveness** | Yêu cầu gốc có được đáp ứng theo scope và kỳ? | FAIL trên hai endpoint legacy. |
| **Exception authorization** | Phê duyệt có đúng nguồn, phạm vi, thẩm quyền, điều kiện và hạn? | PASS trong kỳ quyết định còn hiệu lực. |
| **Compensating control effectiveness** | Các biện pháp thay thế được kiểm chứng và không có bypass quan trọng? | PASS/FAIL/INCONCLUSIVE theo test. |
| **Remediation progress** | Root cause đã được sửa, rollout đúng phạm vi và retest? | IN_PROGRESS hoặc VERIFIED_PASS. |
| **External compliance applicability** | Yêu cầu bên ngoài có cho phép cơ chế thay thế/miễn trừ này? | PASS/FAIL/INCONCLUSIVE từ đánh giá riêng. |

**Quy tắc kết luận:**

- **PASS:** evidence phù hợp chứng minh tiêu chí cụ thể đạt.
- **FAIL:** evidence đáng tin chỉ ra tiêu chí không đạt.
- **INCONCLUSIVE:** không đủ bằng chứng, source không đáng tin hoặc phạm vi chưa rõ.
- **NOT_APPLICABLE:** control thật sự không thuộc phạm vi, có căn cứ và phê duyệt; không dùng cho một ngoại lệ đang hoạt động.

Ví dụ: **control gốc FAIL**, **approval PASS**, **mitigation PASS**, **external compliance INCONCLUSIVE** có thể cùng đúng. Tổng thể không được báo “fully compliant” khi chưa giải quyết phần còn lại.

### 15.1. Không xóa sự thật lịch sử

Một ngoại lệ có hiệu lực ngày 10 đến 30 không hợp thức hóa tự động giai đoạn ngày 1–9 nếu yêu cầu áp dụng từ ngày 1. Sửa control ngày 25 không làm thời kỳ trước đó thành PASS. Báo cáo phải giữ **history theo thời điểm**, original test, các lần renewal và closure.

## 16. Emergency exception và break-glass

Trong incident hoặc DR, đội phản ứng có thể phải dùng quyền/tuyến truy cập ngoài quy trình chuẩn để cô lập hoặc phục hồi dịch vụ. Nếu không có đường khẩn cấp được thiết kế, những thao tác này dễ biến thành ngoại lệ không hồ sơ. Nếu thiết kế quá dễ, break-glass có thể trở thành đường truy cập thường trực.

### 16.1. Những điều kiện nên định nghĩa sẵn

- **Trigger:** mức incident, tình trạng dịch vụ, thiệt hại cần ngăn và lý do không thể chờ phê duyệt thường.
- **Thẩm quyền:** Incident Commander hoặc người được ủy quyền rõ, người thay thế khi mất liên lạc.
- **Scope/TTL:** quyền tạm, đối tượng, account, asset và duration tối thiểu.
- **Security guardrails:** MFA nếu khả thi, danh tính cá nhân, session audit, kênh giao tiếp dự phòng, dual control khi mức rủi ro yêu cầu.
- **Evidence:** incident ID, lệnh/thay đổi, người thực hiện, timestamp, dữ liệu trước/sau và kết quả.
- **Review:** hậu kiểm đúng thời hạn chính sách, thu hồi quyền, kiểm tra session/token và xử lý sai phạm.
- **Remediation:** giải quyết nguyên nhân khiến phải bypass hoặc dùng break-glass lặp lại.

### 16.2. Emergency không đồng nghĩa phê duyệt vô hạn

Nếu một service account được nâng quyền để xử lý incident, sau sự cố phải **revoke, rotate secret nếu cần, kiểm tra hiệu lực quyền và log**, không chỉ đóng incident ticket. Một lần xem xét hậu kiểm trung thực ghi rõ thời điểm thao tác, thẩm quyền khẩn, phần nào ngoài quy trình và rủi ro còn lại; không tạo phê duyệt hồi tố giả.

### 16.3. Một tình huống cần từ chối

Khi nhóm phát triển nói “nếu không tắt log bảo mật trong production thì release sẽ trễ”, đó **không tự tạo emergency authorization**. Phải đánh giá tác động, giải pháp khác và yêu cầu logging; có thể quyết định hoãn release hoặc dùng test environment thay vì chấp nhận bỏ khả năng điều tra cho hệ thống đang xử lý dữ liệu quan trọng.

## 17. Security exception trong Cloud, CI/CD và Third-party Assurance

### 17.1. Cloud/IAM exceptions

Các control cloud thường theo **account, region, identity, resource và đường truy cập**. Một exception cho role quản trị ở account A không tự cho phép role đó ở account B hoặc vùng mới. Khi cloud policy được đưa vào IaC, cần cơ chế **exception ID, resource binding và expiry** được kiểm soát; không tạo hardcoded allowlist vô hạn nằm ngoài GRC.

Ví dụ một policy-as-code gate phát hiện bucket cho phép public access. Không nên tự động thêm tên bucket vào danh sách bỏ qua chỉ để pipeline xanh. Workflow phải xác nhận data classification, quyền của requestor, risk approval, detection và thời hạn; khi hết hạn cần mở lại vi phạm hoặc chặn cấu hình theo quy tắc phê duyệt.

### 17.2. Secure SDLC exceptions

Một đội phần mềm muốn phát hành khi chưa hoàn tất kiểm thử bảo mật hoặc vẫn còn lỗ hổng mức cao. Cần mô tả tính năng, dữ liệu, exposure, threat scenario, scan/test coverage, feature flag, canary, rollback, owner và retest deadline. Một PR đã merge không chứng minh mitigation trong production hoạt động.

Không dùng security exception để cho qua những yêu cầu release bắt buộc về pháp luật/hợp đồng nếu không có quyền cho phép. Phân biệt **temporary release risk decision** và **kết quả security testing** để báo cáo minh bạch.

### 17.3. Vendor và subprocessor

Khi một SaaS thiếu báo cáo audit hoặc chưa đáp ứng điều khoản bảo mật, **risk acceptance nội bộ chỉ xử lý phần rủi ro tổ chức được quyền nhận**, không tự sửa cam kết giữa các bên. Cần phân biệt vendor control failure với **evidence gap**, tham vấn Procurement/Legal, kiểm tra data flow và xác định quyền thay thế nhà cung cấp.

Nếu nhà cung cấp thêm subprocessor, không được suy từ một exception cũ cho SaaS chính ra quyền xử lý dữ liệu mới. Xem mục đích xử lý, địa điểm, quyền truy cập và cơ chế thông báo/ủy quyền theo quan hệ và luật áp dụng.

### 17.4. Bảo mật và an toàn vận hành

Trong hạ tầng trọng yếu hoặc OT, việc cập nhật gấp có thể tạo rủi ro an toàn/gián đoạn. Khi xin patch exception, cần tham vấn owner nghiệp vụ/OT, lập điều kiện segmentation, vendor support, thử trong môi trường phù hợp, cửa sổ bảo trì và phương án ứng phó. Không lấy lý do “không thể dừng” để bỏ monitoring vô thời hạn.

## 18. Automation và hệ thống quản lý ngoại lệ

Một hệ thống GRC, ticketing hoặc policy-as-code có thể tự động hóa luồng request, kiểm tra điều kiện, lưu phê duyệt, giám sát hạn và tạo evidence. Automation chỉ hữu ích nếu **không làm mất quyền quyết định và khả năng giải trình**.

~~~mermaid
flowchart LR
    A["Asset inventory + policy engine"] --> B["Deviation detection"]
    B --> C["Exception register / workflow"]
    D["Requestor, Control Owner, Risk Owner"] --> C
    C --> E["Approval + scope + expiry rules"]
    E --> F["Policy enforcement / monitored allowlist"]
    F --> G["Continuous evidence + drift alerts"]
    G --> H["Review / renewal / revoke / closure"]
    H --> C
    I["Finding + remediation action plan"] --> C
~~~

### 18.1. Những kiểm tra tự động nên có

1. **Schema validation:** control ID, asset IDs, owner, risk, reviewer, dates, scope không rỗng.
2. **Authorization:** người phê duyệt đúng vai trò và mức rủi ro theo policy, không self-approve ngoài quy định.
3. **Time validation:** effective date và expiry hợp lệ, không auto-renew không có quyết định.
4. **Scope binding:** chỉ những asset/policy đã duyệt được phép vượt rule; asset mới phải request riêng.
5. **Control verification:** chứng cứ mitigation đạt; nếu mất phải đánh dấu và gửi alert.
6. **Reassessment triggers:** thay đổi identity, data, region, network, severity hoặc threat.
7. **Evidence lineage:** link nguồn, version, timestamp, reviewer, test method và decision log.
8. **Closure gate:** chỉ chuyển trạng thái khắc phục hoàn tất sau retest và sign-off.
9. **Access control:** không ai có quyền sửa lịch sử phê duyệt lẫn toàn bộ audit log mà không có giám sát.
10. **Failure path:** khi GRC không sẵn sàng, có phương án thủ công được phép và đồng bộ hồ sơ sau đó.

### 18.2. Ví dụ quy tắc kiểm tra, không phải policy chuẩn

~~~text
IF deviation_detected AND no_valid_exception_for_exact_scope:
    create_finding()
    notify_control_owner()
    apply_enforcement_policy_if_authorized()

IF exception_state == ACTIVE:
    verify_effective_dates()
    verify_compensating_controls()
    verify_asset_scope()
    check_reassessment_triggers()

IF expired OR mitigation_failed OR scope_changed_unapproved:
    flag_exception_for_immediate_review()
    initiate_containment_or_enforcement_per_approved_runbook()
    retain_original_decision_and_evidence()
~~~

Không tự động tắt một dịch vụ trọng yếu chỉ vì GRC hết hạn nếu chưa có **enforcement policy và runbook được phê duyệt**; ngược lại, không tự động gia hạn ngoại lệ do sợ gián đoạn. Hệ thống có thể cảnh báo, ngăn triển khai mới, giảm quyền hoặc kích hoạt phê duyệt khẩn theo phương án đã định nghĩa.

## 19. Metrics và reporting cho Exception management

Báo cáo không nên chỉ tối ưu số lượng ngoại lệ đang mở. Một danh mục rất ít ngoại lệ có thể nghĩa là baseline phù hợp, nhưng cũng có thể nghĩa là các đội lách rule không ghi hồ sơ.

| Metric | Câu hỏi trả lời | Lỗi diễn giải thường gặp |
|---|---|---|
| **Open exceptions by risk tier** | Có bao nhiêu rủi ro đang được cho phép, theo phạm vi và mức ảnh hưởng? | Đếm đơn thuần mà bỏ severity và asset criticality. |
| **Expired/unapproved deviations** | Có bao nhiêu trường hợp đang lệch nhưng không có quyền hiệu lực? | Chỉ lọc bản ACTIVE trên dashboard. |
| **Renewal count and age** | Ngoại lệ nào kéo dài, phải gia hạn bao nhiêu lần? | Tự xem gia hạn đúng thủ tục là dấu hiệu rủi ro đã giảm. |
| **Compensating-control verification** | Bao nhiêu ngoại lệ có evidence hiệu lực đúng kỳ và scope? | Đếm control “enabled” nhưng chưa thử. |
| **Scope drift** | Bao nhiêu asset/identity mới bị mở rộng ngoài phạm vi đã duyệt? | Không có inventory đối chiếu độc lập. |
| **Remediation on-time verification** | Bao nhiêu nguyên nhân gốc được sửa và retest đạt đúng hạn? | Đếm ticket đóng thay vì verified closure. |
| **Evidence completeness/freshness** | Hồ sơ có control, risk, approval, mitigation, monitoring, expiry, test? | Các ô đầy đủ không có nghĩa dữ liệu chính xác. |
| **Risk concentration** | Ngoại lệ có tập trung ở một account, service, vendor hoặc control? | Nhìn mean chung bỏ sót điểm nóng nghiêm trọng. |
| **Exception recurrence** | Cùng lỗi có tái xuất hiện sau closure hoặc lặp giữa các team? | Gộp mọi trường hợp giống tên nhưng khác root cause. |
| **Unauthorized bypasses found** | Có bao nhiêu bypass policy chưa được ghi nhận? | Không đầu tư detection làm số thấp giả. |

### 19.1. Ví dụ đọc dashboard

Giả sử có 50 hồ sơ ngoại lệ trong danh mục: 30 ACTIVE đúng hạn, 8 EXPIRED, 7 PENDING và 5 CLOSED có evidence.

- **Active ratio:** 30/50 = 60% hồ sơ, **không** có nghĩa 60% hệ thống an toàn.
- **Expired ratio:** 8/50 = 16%, cần escalation theo mức rủi ro.
- **Pending ratio:** 7/50 = 14%, chưa có quyền mặc định đi ngược baseline.
- **Closed ratio:** 5/50 = 10%, chỉ gọi verified fixed nếu hồ sơ đóng có retest.
- Nếu trong 30 ACTIVE có 20 hồ sơ yêu cầu kiểm soát bù trừ nhưng 4 thiếu test hiệu lực, **verification coverage** của nhóm này là 16/20 = 80%, không tự coi 4 hồ sơ còn lại an toàn.

Mẫu số phải thể hiện rõ hồ sơ, asset hay risk scenario. Một ngoại lệ có thể bao phủ một hoặc hàng trăm asset; **đếm exception IDs không thay thế phân tích phạm vi phơi nhiễm**.

### 19.2. Báo cáo cho các vai trò khác nhau

- **Operations:** asset, điều kiện kỹ thuật, detection, expiry, công việc tới hạn.
- **Security Assurance:** original control result, evidence quality, compensating test, exception condition và retest.
- **Risk Owner/Management:** risk tier, tổng phơi nhiễm, nghĩa vụ liên quan, quyết định cần ký, root-cause backlog.
- **Legal/Compliance:** trường hợp có thể không đáp ứng nguồn yêu cầu bên ngoài và nghĩa vụ xử lý.
- **Audit:** history, approver authority, source evidence, thay đổi scope, findings và closure proof.

### 19.3. Chống làm đẹp số liệu

Đổi severity xuống, tách một ngoại lệ thành nhiều hồ sơ nhỏ để né approval, hoặc dời hạn không lưu lý do đều làm sai báo cáo. Cần giữ **original risk rating, original expiry, lịch sử renewal, phạm vi asset và approvals**, kèm khả năng reviewer truy vết.

## 20. Mẫu hồ sơ Security exception dạng YAML

Đây là **mẫu minh họa**, không phải schema bắt buộc hoặc cấu hình được đưa thẳng lên production. Tên, mốc và số liệu giả định để người học hình dung cách liên kết rủi ro, phê duyệt và bằng chứng.

~~~yaml
security_exception:
  id: "SEC-EXCEPTION-EXAMPLE-001"
  version: "1.0"
  title: "Legacy administration endpoint lacks native MFA"
  created_at_utc: "2026-11-28T03:00:00Z"
  state: "UNDER_REVIEW"
  requested_by: "Legacy Service Owner"

requirement:
  control_id: "IAM-MFA-ADM-EXAMPLE"
  source: "INTERNAL-SECURITY-STANDARD"
  source_version: "2026.4"
  description: "Privileged interactive access requires approved MFA"
  original_control_assessment: "FAIL_ON_TESTED_SCOPE"
  exception_authority_verified: true
  external_obligation_review: "PENDING"

scope:
  environment: "production"
  application: "legacy-operations-console"
  assets:
    - "legacy-admin-01"
    - "legacy-admin-02"
  identities: "Approved named human administrators only"
  entry_point: "managed-bastion"
  region: "region-example-a"
  data_classification: "CONFIDENTIAL"
  prohibited_paths:
    - "direct-ssh-from-untrusted-subnets"
    - "unmanaged-third-party-support"

risk:
  threat_scenario: "Credential theft leading to unauthorized privileged access"
  inherent_level: "HIGH"
  residual_level: "PENDING_VALIDATION"
  risk_assessed_at_utc: "2026-11-28T04:00:00Z"
  decision_authority: "Business Risk Owner"
  applicability_limits:
    - "Legal and contractual constraints must be checked separately"

compensating_controls:
  - id: "CC-MFA-BASTION"
    design: "MFA enforced before each qualifying privileged session"
    owner: "Identity Platform Team"
    test_status: "PASS_ON_TESTED_PATH"
    evidence: "restricted/exception-001/bastion-mfa-test"
  - id: "CC-DIRECT-ACCESS-DENY"
    design: "Prevent all unmanaged direct administration paths"
    owner: "Network Security Team"
    test_status: "INCONCLUSIVE"
    evidence: "restricted/exception-001/network-path-review"
  - id: "CC-PRIVILEGED-AUDIT"
    design: "Collect privileged session logs and alert on anomalies"
    owner: "Security Monitoring Team"
    test_status: "PASS_ON_TESTED_SCOPE"
    evidence: "restricted/exception-001/synthetic-alert"

authorization:
  review_status: "PENDING"
  control_owner: "IAM Policy Owner"
  security_assessor: "Security Assurance Reviewer"
  business_risk_owner: "Legacy Business Owner"
  legal_compliance_review: "NOT_COMPLETED"
  approved_at_utc: null
  effective_from_utc: null
  expires_at_utc: null
  conditions:
    - "No direct admin path may remain open"
    - "Monitoring must remain available"
    - "Review after any new administrative identity"

remediation:
  finding_id: "F-IAM-EXAMPLE-001"
  action_plan_id: "ACTION-PLAN-EXAMPLE-001"
  owner: "Application Modernization Team"
  target: "Replace legacy module with supported MFA enforcement"
  milestone_tracking: "REQUIRED"
  retest:
    method: "Verify privileged paths, effective policies, bypass denial"
    reviewer: "Independent Security Assurance Reviewer"
    status: "NOT_STARTED"

monitoring:
  verify_scope_drift: true
  watch_compensating_controls: true
  reassessment_triggers:
    - "bastion-mfa-failure"
    - "new-asset-or-admin-route"
    - "security-incident"
    - "threat-escalation"
  next_review: "AFTER_MISSING_EVIDENCE_RESOLVED"

assurance:
  original_control: "FAIL"
  exception_authorization: "INCONCLUSIVE"
  compensating_controls: "INCONCLUSIVE"
  external_compliance: "INCONCLUSIVE"
  overall_decision: "NOT_AUTHORIZED"
  evidence_vault: "restricted-security-assurance"
  version_history_preserved: true
~~~

### 20.1. Vì sao mẫu chưa được phê duyệt?

Bastion MFA đã có test trên đường được quan sát, nhưng **direct administration denial chưa đủ bằng chứng**. Đồng thời, legal/contract review và owner authorization chưa hoàn tất. Vì vậy trạng thái **UNDER_REVIEW** và **NOT_AUTHORIZED** phản ánh đúng thực tế. Không được tự đặt `ACTIVE` chỉ vì một số compensating controls có `PASS`.

### 20.2. Điều chỉnh khi có quyết định chấp thuận

Khi các điều kiện bắt buộc đã đạt và được người có quyền quyết định:

- Ghi chính xác approver identity, timestamp và decision reference.
- Chốt effective/expiry, kiểm tra không có khoảng thời gian ngoài phê duyệt.
- Gắn các action plan milestones có người chịu trách nhiệm.
- Lưu raw evidence cho các test đường bypass, audit và quyền.
- Định nghĩa trigger thu hồi và kế hoạch retest control gốc.
- Giữ nguyên `original_control` nếu nó vẫn FAIL theo tiêu chí.

### 20.3. Khi phải từ chối

Nếu không chặn được đường quản trị trực tiếp hoặc nghĩa vụ bên ngoài không cho phép lệch, kết quả phù hợp là **REJECTED/REQUIRES_REMEDIATION**, cùng quyết định containment hoặc thay đổi kiến trúc. Không tạo “approved with high risk” để bỏ qua điều kiện bắt buộc khi người phê duyệt không có quyền thay đổi chúng.

## 21. Tình huống thực hành: Ngoại lệ bảo mật cho hệ thống thanh toán legacy

Một đơn vị cung cấp dịch vụ thanh toán vận hành ứng dụng quản trị cũ trên hai máy chủ production. Security standard nội bộ yêu cầu privileged access qua SSO và MFA, audit log quản trị được gửi đến SIEM, và mọi vulnerability mức nghiêm trọng được khắc phục theo hạn của chính sách.

Nhóm sản phẩm đề nghị ngoại lệ **120 ngày** vì nâng cấp ứng dụng có nguy cơ gián đoạn giao dịch. Họ đưa ra các bằng chứng:

- Tài khoản nhân viên nội bộ dùng VPN có MFA; nhưng quản trị viên nhà thầu có thể kết nối qua đường hỗ trợ riêng chưa được rà soát.
- Một service account quản trị có token dài hạn, chưa có owner xác nhận.
- Chỉ máy chủ thứ nhất gửi đủ session audit tới SIEM; máy thứ hai không có log tương ứng trong kiểm tra.
- Nhóm Network nói firewall đã chặn direct admin access, nhưng không cung cấp thử truy cập từ subnet nhà thầu.
- Kế hoạch nâng cấp có mốc triển khai nhưng chưa có rollback và test quy trình giao dịch.
- Service Owner phê duyệt request trong ticket; policy xác định rủi ro mức cao cần phê duyệt của Business Risk Owner và Security review độc lập.
- Hợp đồng với đối tác thanh toán có điều khoản an toàn riêng, chưa được Legal/Compliance đối chiếu.
- Trong kỳ có cảnh báo credential stuffing đối với cổng hỗ trợ, chưa xác nhận có thành công hay không.

### 21.1. Câu hỏi

1. Có đủ căn cứ để kích hoạt ngoại lệ 120 ngày chưa? Vì sao?
2. Những rủi ro và đường truy cập nào bị bỏ sót?
3. Compensating controls nào đang FAIL, INCONCLUSIVE hoặc PASS trên scope hẹp?
4. Người nào phải tham gia quyết định? Những điều kiện pháp lý/hợp đồng nào phải rà?
5. Nếu cần duy trì dịch vụ trong ngắn hạn, có thể giảm rủi ro bằng phương án gì?
6. Cần tiêu chí và bằng chứng nào để đóng ngoại lệ sau nâng cấp?

### 21.2. Hướng giải chi tiết

**Bước 1 — Chốt requirement và scope.** Tách kiểm soát SSO/MFA, logging và vulnerability remediation thành các claim hoặc finding riêng; liên kết chúng trong một chương trình remediation nhưng **không cấp waiver bao trùm** thiếu kiểm soát từng mục. Kiểm kê cả human administrators, contractor access, long-lived tokens, hai máy chủ, VPN, bastion, direct route và dịch vụ liên quan.

**Bước 2 — Kiểm tra đường vào quản trị.** MFA của VPN cho nhân viên không bảo vệ đường hỗ trợ nhà thầu nếu đường đó không đi qua cùng enforcement. Cần network/access-flow map và test denied/allowed path theo phạm vi được cho phép. Service account token dài hạn cần risk review và chính sách quản lý machine identities, không được vô tình loại vì chỉ đánh giá human users.

**Bước 3 — Phân loại control bù trừ.** VPN MFA có thể **PASS trên nhóm nhân viên được thử**, nhưng bảo vệ toàn bộ privileged access **INCONCLUSIVE** vì support path chưa rõ. Logging continuity có thể **FAIL** cho máy thứ hai nếu chứng minh sự kiện không đến SIEM theo tiêu chí; nếu chỉ thiếu quyền quan sát, tách evidence gap để điều tra. Firewall control **INCONCLUSIVE** nếu chưa có test đường bypass phù hợp.

**Bước 4 — Kiểm tra rủi ro và incident.** Cảnh báo credential stuffing là trigger xem xét mức phơi nhiễm và có thể kích hoạt incident triage. Nếu xác nhận xâm nhập, ưu tiên containment/IR chứ không tiếp tục quy trình ngoại lệ thông thường như không có gì xảy ra. Việc không thấy bằng chứng truy cập thành công chưa chứng minh không có xâm nhập nếu log thiếu.

**Bước 5 — Xác minh thẩm quyền và nghĩa vụ.** Service Owner chưa có quyền phê duyệt ngoại lệ rủi ro cao theo chính sách. Cần Security/Risk review và quyết định của Business Risk Owner; Legal/Compliance phải đánh giá điều khoản đối tác. Không thể dùng phê duyệt nội bộ để thay đổi hợp đồng khi điều khoản không cho phép.

**Bước 6 — Giảm rủi ro tức thời.** Có thể giới hạn hoặc tạm khóa đường support chưa được xác minh, bắt buộc nhà thầu qua bastion có MFA, rotate/revoke token quá hạn, sửa log pipeline, tăng alert và giới hạn nguồn kết nối. Mọi biện pháp phải có test hiệu lực và kế hoạch rollback phù hợp nghiệp vụ.

**Bước 7 — Thiết kế action plan.** Chốt owner/mốc cho nâng cấp, test giao dịch end-to-end, bảo toàn dữ liệu, kế hoạch triển khai có kiểm soát, điều kiện dừng và independent retest. Nếu vẫn có rủi ro ngoài ngưỡng hoặc nghĩa vụ không cho phép, xem xét hạn chế tính năng, thay giải pháp hoặc xử lý hợp đồng theo quyền hợp lệ.

### 21.3. Bảng kết luận tại thời điểm đề nghị

| Tiêu chí | Tình trạng | Kết luận minh họa |
|---|---|---|
| **Phê duyệt có thẩm quyền** | Chỉ Service Owner ký, thiếu required review. | **FAIL** nếu coi đã được duyệt; hiện tại request chưa được cho phép. |
| **MFA toàn bộ privileged paths** | VPN của nhân viên có MFA, contractor path chưa kiểm. | **INCONCLUSIVE** cho toàn scope. |
| **Long-lived privileged token** | Chưa có owner, kiểm soát hiệu lực chưa xác minh. | **INCONCLUSIVE / finding cần điều tra**. |
| **Audit logging đầy đủ** | Máy thứ hai không có log trong phép kiểm tra. | **FAIL nếu thiếu end-to-end events đã xác minh; nếu nguồn chưa kiểm được, evidence gap**. |
| **Chặn đường quản trị trực tiếp** | Có lời xác nhận, thiếu negative-path test. | **INCONCLUSIVE**. |
| **Residual risk** | Chưa đánh giá contractor và cảnh báo tấn công. | **INCONCLUSIVE**. |
| **Nghĩa vụ hợp đồng** | Chưa review. | **INCONCLUSIVE**; chưa xác nhận quyền ngoại lệ. |
| **Remediation readiness** | Thiếu rollback và test giao dịch. | **FAIL** theo điều kiện kế hoạch sẵn sàng nếu được yêu cầu. |

**Kết luận:** Chưa thể kích hoạt ngoại lệ 120 ngày với bộ thông tin hiện tại. Cần đánh giá quyền, ngăn bypass, giải quyết logging/token, xem cảnh báo sự cố và hoàn thiện legal/risk review. Những hành động khẩn cấp để bảo vệ dịch vụ phải tuân thủ cơ chế khẩn được phép, không giả làm ngoại lệ đã phê duyệt.

## 22. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Gọi mọi finding là security exception. | Mất phân biệt tình trạng lỗi và quyền cho phép. | Tách deviation/finding/request/approval/result. |
| Dùng ngoại lệ để đổi control FAIL thành PASS. | Báo cáo assurance sai thực tế. | Lưu các trục control, approval và mitigation riêng. |
| Không xác định nguồn requirement. | Một người nội bộ có thể “miễn” yêu cầu ngoài quyền. | Applicability + authority review trước phê duyệt. |
| Scope ghi “mọi hệ thống liên quan”. | Ngoại lệ mở rộng ngoài kiểm soát. | Asset IDs, identities, data, action và time cụ thể. |
| Chấp nhận rủi ro theo cảm giác. | Bỏ threat scenario, exposure và impact. | Risk assessment với evidence, phương pháp và owner. |
| Chỉ có lời hứa về compensating control. | Residual risk thấp hơn thực tế. | Test effective control và bypass paths. |
| Không thử đường nhà thầu/break-glass. | MFA/bastion bị bypass. | Access path inventory và test theo phạm vi. |
| Không review khi thêm tài sản mới. | Asset mới hưởng waiver cũ ngoài scope. | Inventory drift trigger và scope binding. |
| Đặt expiry “khi có patch”. | Ngoại lệ kéo dài vô hạn. | Expiry cụ thể, milestones và escalation. |
| Gia hạn tự động. | Rủi ro mới không được đánh giá. | Reassessment, control retest và approval có version. |
| Hết hạn nhưng dashboard vẫn ACTIVE. | Vận hành lệch chuẩn không có quyền hiện hành. | Scheduler, alert, action runbook và decision log. |
| Một người tự đề xuất, tự duyệt và tự xác minh. | Xung đột lợi ích, thiếu accountability. | Segregation of duties theo risk tier. |
| Chỉ xem monitoring policy có tồn tại. | Không biết log thực sự tới SIEM hay không. | Synthetic end-to-end evidence và alert test. |
| Đóng exception vì PR merge. | Fix chưa deploy đủ scope, control vẫn sai. | Production verification và independent retest. |
| Không phân biệt giai đoạn được cho phép và giai đoạn không được duyệt. | Che lịch sử noncompliance. | Version/time history, effective/expiry và audit trail. |
| Dùng mẫu vendor chung cho mọi tenant. | Không biết cấu hình thực hoặc external obligations. | Shared responsibility mapping và customer evidence. |
| Chấp nhận risk mãi vì business impact. | Mất động lực xử lý nguyên nhân. | Root-cause plan, owner, mốc review và alternative design. |

## 23. Checklist đánh giá Security exception

Một reviewer có thể dùng checklist sau để quyết định một hồ sơ đã đủ điều kiện trình phê duyệt, giám sát hay đóng:

1. **Control:** Có source, ID, version và tiêu chí gốc được xác định chính xác?
2. **Applicability:** Đã kiểm tra luật, hợp đồng, chuẩn/chương trình và quyền cho phép ngoại lệ?
3. **Observed gap:** Có bằng chứng control chưa đạt, phân biệt với thiếu evidence?
4. **Scope:** Có asset IDs, environment, identity, entry points, dữ liệu, region và kỳ rõ?
5. **Reason:** Có root cause, lý do không sửa ngay và lựa chọn thay thế đã xét?
6. **Risk:** Có threat scenario, impact, exposure, inherent/residual risk theo phương pháp tổ chức?
7. **Controls:** Compensating measures có owner, test, phạm vi, limitation và monitor?
8. **Bypass:** Đã kiểm thử đường không được phép, break-glass, contractor và machine identities theo yêu cầu?
9. **Authorization:** Người duyệt có đúng thẩm quyền; Security/Legal/Compliance đã tham gia khi cần?
10. **Decision:** Quyết định có điều kiện cụ thể, timestamp, version và sign-off đáng tin?
11. **Validity:** Effective/expiry, review dates, remediation milestones và ownership có rõ?
12. **Monitoring:** Có phát hiện mitigation lỗi, scope drift, threat mới, incident và deadline miss?
13. **Evidence:** Có source, timestamp, test IDs, raw/derived lineage, integrity và kho phân quyền?
14. **State:** Request pending, approved, active, expired, revoked và closed có được phân biệt đúng?
15. **Emergency:** Có đường xử lý khẩn với TTL, logging, thu hồi quyền và hậu kiểm?
16. **Remediation:** Có kế hoạch sửa nguyên nhân, dependency, rollback/change gate và tiêu chí retest?
17. **Assurance:** Có kết luận riêng về control gốc, exception governance, mitigation và nghĩa vụ bên ngoài?
18. **Closure:** Đã verify fix hoặc xử lý rủi ro bằng phương án hợp lệ, không chỉ ticket done?
19. **History:** Đã lưu khoảng thời gian FAIL/không được phê duyệt, gia hạn và kết quả sau sửa?
20. **Continuous improvement:** Có báo cáo overdue, recurrence, risk concentration và cải tiến baseline để giảm ngoại lệ lặp lại?

### Câu hỏi tự đánh giá

Một đội platform được phê duyệt ngoại lệ 60 ngày cho một máy chủ không thể vá kịp, với điều kiện chỉ truy cập từ subnet quản trị, có EDR và alert trong SIEM. Ngày thứ 40, máy chủ được đưa vào một subnet mới phục vụ đối tác. Đồng thời EDR offline hai ngày, nhưng chưa thấy alert xâm nhập. Ngày thứ 55, đội vận hành đề nghị gia hạn thêm 90 ngày.

**Có thể phê duyệt gia hạn chỉ vì exception ban đầu chưa hết hạn và chưa có cảnh báo xâm nhập không?**

**Gợi ý:** Không. Scope mạng đã thay đổi và compensating control mất hiệu lực, là những trigger **đánh giá lại ngay** thay vì đợi hết hạn. Thiếu alert không chứng minh không có tấn công khi EDR/SIEM có khoảng mù. Cần xác minh exposure mới, khôi phục EDR và thử end-to-end, xem log nguồn khác hoặc incident triage khi phù hợp, đánh giá rủi ro cập nhật, thay mitigation, kiểm tra nghĩa vụ áp dụng và remediation progress; chỉ cấp quyết định mới theo đúng quyền khi điều kiện được chứng minh, có hạn và kế hoạch sửa thực tế.

**Security exception có giá trị khi tổ chức thừa nhận trung thực một control gap, xác định chính xác quyền và phạm vi được phép lệch, kiểm chứng các biện pháp giảm rủi ro, duy trì giám sát trong thời gian hiệu lực và buộc vấn đề đi tới remediation hoặc một kết thúc có căn cứ. Một ngoại lệ bảo mật không phải “vé miễn kiểm tra”, mà là một cam kết quản trị có thời hạn, có người chịu trách nhiệm và có bằng chứng để người khác kiểm chứng.**

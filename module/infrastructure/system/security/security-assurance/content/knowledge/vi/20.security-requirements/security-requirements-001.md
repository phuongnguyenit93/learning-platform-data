# Viết security requirement: Chuyển rủi ro thành yêu cầu bảo mật có thể kiểm chứng

## 1. Security requirement là gì?

**Security requirement** (yêu cầu bảo mật) là phát biểu có thể quản lý và xác minh về **thuộc tính, hành vi hoặc ràng buộc bảo mật mà hệ thống, tổ chức, quy trình hoặc thành phần phải đáp ứng** để bảo vệ tài sản và đạt mục tiêu bảo mật trong phạm vi đã xác định.

Ví dụ:

> Khi người dùng gọi API xem đơn hàng, dịch vụ phải chỉ trả về đơn hàng mà danh tính đã được xác minh có quyền truy cập; yêu cầu tới đơn hàng thuộc tenant khác phải bị từ chối mà không tiết lộ dữ liệu của đơn hàng đó.

Phát biểu này nói rõ **khi nào**, **ai/đối tượng nào**, **hành vi bắt buộc**, **ranh giới bảo vệ** và **kết quả có thể quan sát**. Nó có thể trở thành đầu vào cho thiết kế, triển khai, kiểm thử và security assurance.

Ngược lại, câu “Hệ thống phải có bảo mật tốt” không xác định điều kiện kiểm chứng. Hai reviewer có thể hiểu khác nhau và một test không thể chỉ ra được tiêu chí PASS/FAIL.

Trong module **SECURITY_SECURITY_ASSURANCE**, viết security requirement là một mắt xích then chốt:

**Risk/threat → Security objective → Security requirement → Control/implementation → Test/audit → Evidence → Finding → Remediation/retest.**

Nếu requirement mơ hồ, các bước phía sau khó tạo bằng chứng đủ sức thuyết phục. Một test PASS cho tiêu chí không rõ có thể tạo cảm giác an toàn sai.

### 1.1. Một yêu cầu tốt giúp những ai?

- **Product/business owner:** hiểu ranh giới nghiệp vụ và tác động của một quyết định bảo mật.
- **Security architect:** chọn security controls hợp lý và phân bổ trách nhiệm.
- **Developer:** biết điều kiện phải thực thi, kể cả trường hợp lỗi.
- **QA/AppSec:** thiết kế positive/negative test cases có oracle rõ.
- **SRE/operations:** biết khi nào cần cảnh báo, xử lý, khôi phục và giữ bằng chứng.
- **Risk/compliance owner:** truy vết nghĩa vụ và lý do ưu tiên.
- **Assurance/auditor:** đánh giá xem requirement nào đạt, không đạt hoặc chưa đủ evidence.

Yêu cầu bảo mật nên được đọc hiểu bởi những vai trò trên, không phải chỉ bởi tác giả.

### 1.2. Tại sao không nên bắt đầu bằng công cụ?

Một nhóm có thể viết: “Dùng WAF”, “Cài scanner” hoặc “Đặt dữ liệu vào vault”. Đây thường là **lựa chọn control/giải pháp**, chưa phải mục tiêu bảo mật cần bảo đảm.

Ví dụ:

- **Rủi ro:** attacker có thể dùng credential bị lộ để đọc báo cáo nhạy cảm.
- **Security objective:** chỉ danh tính đúng quyền mới được xuất báo cáo.
- **Requirement:** mọi export báo cáo có nhãn Confidential phải được xác thực và kiểm tra authorization theo subject, resource và đích nhận; nếu quyết định không hợp lệ thì không tạo đường tải.
- **Control khả thi:** gateway, application authorization, DLP, audit và policy engine.
- **Tests:** wrong-user, wrong-tenant, wrong-destination, policy-service failure và replay.
- **Evidence:** test result, policy version, audit event và deploy record.

Công cụ là một **phương án thực thi**. Không nên thay toàn bộ security objective bằng tên một sản phẩm.

## 2. Phân biệt requirement với các khái niệm lân cận

| Khái niệm | Câu hỏi | Ví dụ trong Orders API |
| --- | --- | --- |
| **Asset** | Điều gì cần bảo vệ? | Hồ sơ đơn hàng và dữ liệu khách hàng |
| **Threat/risk scenario** | Điều gì có thể xảy ra và gây hại? | User A đổi order ID để xem dữ liệu tenant B |
| **Security objective** | Trạng thái bảo vệ mong muốn? | Không có truy cập trái quyền giữa tenant |
| **Security policy** | Tổ chức quyết định nguyên tắc bảo vệ gì? | Dữ liệu khách hàng chỉ được truy cập bởi chủ thể có thẩm quyền |
| **Security standard/baseline** | Quy tắc chi tiết hoặc tiêu chuẩn tối thiểu nào phải theo? | Các service phải xác minh quyền trên từng resource |
| **Security requirement** | Thành phần trong phạm vi phải thực thi hành vi nào? | API tìm order theo tenant của principal đã xác minh |
| **Security control** | Biện pháp nào thực thi hoặc hỗ trợ yêu cầu? | Authorization guard và tenant-scoped repository |
| **Implementation/design** | Cơ chế kỹ thuật cụ thể ra sao? | Spring Security, service method và scoped query |
| **Acceptance criterion** | Điều gì được tính là đạt? | A đọc A thành công, A đọc B bị từ chối và không có dữ liệu B |
| **Test case** | Kiểm tra điều kiện này bằng thao tác nào? | Gửi token A, gọi GET với order B, assert response/audit |
| **Evidence** | Dữ kiện nào cho thấy điều đã quan sát? | Test run ID, build digest, DB/audit result |
| **Assurance conclusion** | Có thể tin control hiệu quả đến đâu? | Đạt với các API đã test trên build và môi trường xác định |

**Security requirement không phải test case.** Requirement ổn định hơn một test cụ thể; nhiều phương pháp có thể cùng kiểm chứng một requirement.

**Security requirement cũng không phải risk acceptance.** Nếu một yêu cầu bắt buộc chưa đáp ứng, quyết định ngoại lệ phải đi theo quy trình có thẩm quyền và không biến yêu cầu chưa đạt thành “đã đạt”.

### 2.1. Requirement so với security objective

Mục tiêu “bảo đảm confidentiality” quá rộng để developer triển khai trực tiếp. Một mục tiêu có thể phân rã thành các yêu cầu:

- Xác thực danh tính người truy cập.
- Kiểm tra quyền theo subject–action–resource–context.
- Giới hạn việc export dữ liệu nhạy cảm.
- Mã hóa dữ liệu khi truyền qua ranh giới nhất định.
- Không đưa thông tin nhạy cảm vào log.
- Giám sát và phản ứng hành vi đọc bất thường.

Mỗi yêu cầu phải có **scope và điều kiện kiểm chứng** riêng.

### 2.2. Requirement so với giải pháp kỹ thuật

Phát biểu “Bắt buộc dùng thư viện X” có thể là **ràng buộc kiến trúc/technology constraint** hợp lệ nếu đã được phê duyệt. Nhưng nếu chưa có lý do bắt buộc, nên mô tả **security property** trước rồi mới chọn công nghệ.

Ví dụ:

- Yêu cầu công nghệ: “Ứng dụng phải dùng cơ chế khóa được nền tảng phê duyệt để quản lý private key ký.”
- Yêu cầu kiểm soát: “Private signing key không được xuất ở dạng bản rõ ra tiến trình không được ủy quyền; mọi thao tác ký phải được kiểm soát quyền và ghi audit.”

Hai yêu cầu có thể bổ sung nhau; đừng bỏ quên thuộc tính bảo mật chỉ vì đã nêu tên giải pháp.

## 3. Nguồn đầu vào để viết security requirement

Một yêu cầu không nên được đặt ra tùy hứng. Nên có **nguồn (source) và rationale** rõ.

### 3.1. Các nguồn thường gặp

1. **Risk assessment:** kịch bản rủi ro, mức ảnh hưởng, khả năng xảy ra và quyết định xử lý.
2. **Threat modeling:** data flow, trust boundary, entry points, attacker capability và abuse cases.
3. **Business requirements:** chức năng, transaction, tác động nghiệp vụ và những hành vi được phép.
4. **Data classification:** loại dữ liệu, mức nhạy cảm, nơi lưu và luồng chia sẻ.
5. **Security policy/standard:** những quy tắc nội bộ đã phê duyệt và phiên bản hiệu lực.
6. **Framework/control catalog:** nguồn tham khảo như OWASP ASVS, NIST SP 800-53 hoặc ISO/IEC 27001, dùng đúng phiên bản và applicability.
7. **Nghĩa vụ pháp lý/hợp đồng:** chỉ áp các yêu cầu **đã được xác nhận thực sự có hiệu lực** cho hệ thống và hoạt động liên quan.
8. **Incidents/pentest/audit findings:** những điểm yếu thực tế và nguyên nhân gốc cần ngăn tái diễn.
9. **Operational needs:** recovery, logging, credential rotation, detection, change management và khả năng bảo trì.

Một control framework cho biết nhóm control đáng cân nhắc, **không tự định nghĩa tiêu chí triển khai của ứng dụng cụ thể**. Phải điều chỉnh cho scope, nguồn dữ liệu và threat model.

### 3.2. Ví dụ nguồn rủi ro

Hệ thống SaaS quản lý đơn hàng của nhiều khách hàng. Dữ liệu nhạy cảm gồm email, địa chỉ và trạng thái thanh toán. Một user hợp lệ có thể thử thay order ID trong URL.

- **Threat actor:** authenticated user của tenant A.
- **Entry point:** GET /api/orders/{id}.
- **Trust boundary:** từ principal A sang tài nguyên được sở hữu bởi tenant B.
- **Attack path:** client gửi ID của order B.
- **Potential impact:** lộ dữ liệu khách hàng tenant B.
- **Existing gap:** API chỉ kiểm tra đăng nhập, chưa kiểm tra quyền trên object.
- **Desired outcome:** không tiết lộ dữ liệu B cho principal A.

Từ đó có thể viết requirement cụ thể. Nếu chỉ ghi “bảo vệ API bằng JWT” thì attacker vẫn có thể dùng **JWT hợp lệ** để vượt quyền.

### 3.3. Cần xác định applicability trước khi phát biểu “phải”

Không phải mọi control đều áp dụng đồng đều cho mọi thành phần.

Ví dụ:

- MFA cho thao tác quản trị đặc quyền có thể được yêu cầu, nhưng không nhất thiết áp dụng y hệt cho mọi machine-to-machine call.
- Retention của audit log phải theo loại log và yêu cầu có hiệu lực, không tự chọn một thời hạn cho tất cả.
- Những ràng buộc về vùng lưu trữ, dữ liệu cá nhân và phép chuyển dữ liệu phụ thuộc jurisdiction, mục đích và vai trò của tổ chức.
- Service không có chức năng tải tệp có thể không cần requirement kiểm tra upload.

Yêu cầu cần ghi **đối tượng, điều kiện áp dụng và lý do không áp dụng** khi cần. Không lấy một ví dụ trong bài làm nghĩa vụ pháp lý hoặc baseline phổ quát.

## 4. Cấu trúc của một security requirement tốt

### 4.1. Công thức viết có thể tái sử dụng

Một mẫu ngôn ngữ tự nhiên:

> **Trong [điều kiện/ngữ cảnh], [hệ thống/thành phần chịu trách nhiệm] phải [hành vi bảo mật quan sát được] đối với [tài sản/hành động/phạm vi], theo [quy tắc/tiêu chí cụ thể]; khi [điều kiện không thỏa/lỗi] thì [hành vi an toàn bắt buộc].**

Ví dụ:

> Khi một request truy cập order được xử lý, Orders API phải xác minh principal và chỉ cho phép thao tác nếu principal có quyền đối với order thuộc tenant đã được xác minh; nếu không xác định được principal, tenant hoặc quyền thì không trả dữ liệu order và ghi sự kiện từ chối theo quy tắc audit đã phê duyệt.

Không phải câu nào cũng cần chứa toàn bộ thành phần trong một đoạn dài. Có thể dùng **requirement ngắn + acceptance criteria** để tăng tính rõ ràng, miễn không tách mất điều kiện quan trọng.

### 4.2. Các thành phần tối thiểu

| Thành phần | Cần thể hiện gì? | Ví dụ |
| --- | --- | --- |
| **Subject/owner của nghĩa vụ** | Thành phần chịu trách nhiệm thực thi | Orders API |
| **Trigger/condition** | Khi nào yêu cầu có hiệu lực | Khi đọc hoặc export order |
| **Actor/context** | Danh tính, role, tenant, trạng thái | Principal đã xác minh của tenant A |
| **Asset/action** | Tài nguyên và thao tác | Order của một tenant |
| **Required behavior** | Hệ thống phải làm gì | Check object-level permission |
| **Forbidden behavior** | Điều gì tuyệt đối không được xảy ra | Không trả dữ liệu của tenant khác |
| **Failure behavior** | Khi không kiểm tra được thì sao | Deny, không fallback sang quyền rộng |
| **Boundary/scope** | API/service/environment/luồng liên quan | GET, export, worker |
| **Verification criterion** | Dựa vào đâu xác định PASS/FAIL | Positive và negative tests, audit |
| **Traceability** | Requirement sinh từ đâu và map tới control nào | Threat ID, policy ref |

Khi yêu cầu có điều kiện định lượng, cần ghi thêm **đơn vị, điểm bắt đầu/kết thúc đo, denominator, cửa sổ thời gian và mức chấp nhận**.

### 4.3. Metadata nên đi cùng requirement

Ngoài nội dung bắt buộc, một hồ sơ requirement có thể có:

- **ID ổn định** và version/revision.
- Tiêu đề ngắn, mô tả và rationale.
- Source refs: risk, threat, objective, policy, standard hoặc nghĩa vụ có áp dụng.
- Asset/data class/trust boundary và phạm vi hệ thống.
- Requirement type, priority, risk impact.
- **Owner/accountable** và reviewer/approver.
- Applicability, preconditions và dependencies.
- Acceptance criteria, verification method, evidence expectations.
- Status: Draft, Reviewed, Approved, Implemented, Verified, Deprecated.
- Effective date, review date và change history.
- Exception/residual-risk reference khi có.

Không biến metadata thành tài liệu quá nặng khiến yêu cầu không được cập nhật. Chọn những trường hỗ trợ quyết định và traceability thực tế.

## 5. Những đặc tính tạo ra requirement chất lượng

### 5.1. Rõ ràng và đơn nghĩa

Tránh các từ chưa có định nghĩa:

- “Bảo mật mạnh”.
- “Phù hợp tiêu chuẩn tốt nhất”.
- “Nhanh chóng”.
- “Đủ an toàn”.
- “Mã hóa thích hợp”.
- “User có thẩm quyền”.
- “Không lưu quá lâu”.

Nếu dùng các khái niệm này, phải **định nghĩa chuẩn tham chiếu hoặc tiêu chí cụ thể**.

Thay vì “xử lý sự cố nhanh”, có thể viết: “Security operations phải chuyển cấp các alert thuộc loại Critical tới on-call trong thời gian đã được phê duyệt cho loại alert này; thời điểm phát sinh, nhận, chuyển cấp và kết quả phải được ghi để kiểm chứng.” Nếu có target thời gian, nêu rõ nguồn và thời điểm đo.

### 5.2. Atomic – mỗi requirement tập trung một nghĩa vụ

Một câu quá dài có thể chứa mười yêu cầu: xác thực, phân quyền, mã hóa, log, backup và retention. Khi một phần không đạt, không biết status cho cả câu là gì.

Nên tách:

- SEC-AUTH-001: xác thực danh tính.
- SEC-AUTHZ-001: kiểm tra quyền theo resource.
- SEC-DATA-001: bảo vệ dữ liệu khi truyền.
- SEC-AUDIT-001: ghi event truy cập nhạy cảm.
- SEC-RET-001: xử lý dữ liệu quá thời hạn lưu.

**Atomic không có nghĩa bỏ quan hệ phụ thuộc.** Ví dụ authorization có thể phụ thuộc authentication. Ghi dependency thay vì ghép hai yêu cầu thành một câu không kiểm thử riêng được.

### 5.3. Testable – có oracle

**Test oracle** là tiêu chí xác định kết quả đúng/sai.

Ví dụ cho yêu cầu tenant isolation:

- Có order A/B và user A/B.
- A đọc A → thành công.
- A đọc B → không trả nội dung B.
- Nếu principal/tenant không hợp lệ → deny theo policy.
- Database và cache không để lộ record B.
- Audit nhận event theo thiết kế.

Một requirement có thể cần nhiều test ở nhiều tầng; không bắt buộc chỉ một assertion.

### 5.4. Feasible và consistent

Yêu cầu cần khả thi về kỹ thuật, phù hợp mô hình nghiệp vụ và không mâu thuẫn.

Ví dụ:

- “Không được lưu dữ liệu cá nhân dưới mọi hình thức” mâu thuẫn với chức năng giao hàng cần địa chỉ.
- “Mọi request phải có MFA tương tác” có thể không phù hợp với service-to-service.
- “Xóa mọi backup ngay khi user gửi yêu cầu” có thể không khả thi hoặc mâu thuẫn nghĩa vụ lưu giữ đã xác nhận.

Cần điều chỉnh bằng điều kiện áp dụng, mục đích, retention/exception, thời điểm và control thay thế. **Feasible không phải lý do mặc định để hạ thấp yêu cầu bắt buộc**; nếu không thể đáp ứng, phải xử lý rủi ro qua đúng quy trình.

### 5.5. Necessary và traceable

Requirement phải phục vụ mục tiêu hay nghĩa vụ xác định. Nếu không giải thích được **vì sao** cần một yêu cầu, review lại:

- Có threat/risk nào liên quan không?
- Có nguồn policy/standard/hợp đồng thực sự áp dụng?
- Có requirement khác đã bao phủ?
- Đây là outcome bảo mật hay chỉ lựa chọn giải pháp theo thói quen?
- Có phù hợp với data classification và trust boundary?

### 5.6. Verifiable in the right environment

Một unit test của một method có thể PASS trong khi security filter bị tắt trên production. Requirement cần chỉ rõ **phạm vi verification**, và assessment phải lưu build, environment, policy version, runtime evidence khi phù hợp.

Không nhất thiết viết tất cả metadata trong câu requirement; có thể dùng test plan và evidence record liên kết.

## 6. Chuyển câu mơ hồ thành requirement có thể kiểm chứng

| Câu chưa tốt | Vấn đề | Cách viết rõ hơn |
| --- | --- | --- |
| “Ứng dụng phải an toàn.” | Không có hành vi/tiêu chí | “Các thao tác đọc order phải kiểm tra quyền trên order và tenant của principal đã xác minh.” |
| “Phải có bảo mật đăng nhập tốt.” | “Tốt” không định nghĩa | “Tài khoản bị vô hiệu không được tạo session mới; token/session liên quan được xử lý theo policy thu hồi.” |
| “Mã hóa mọi thứ.” | Quá rộng, thiếu scope | “Dữ liệu nhãn Confidential khi truyền giữa client và Orders API phải dùng giao thức vận chuyển mã hóa được baseline phiên bản X phê duyệt.” |
| “Dùng JWT.” | Tên công nghệ không đủ | “API phải xác minh issuer, signature, audience, expiry và các claims bắt buộc của access token trước khi cho phép hành động được bảo vệ.” |
| “Ghi log đủ.” | Không xác định event/metadata | “Mọi thao tác export thành công/thất bại phải ghi actor, action, resource scope, thời điểm và outcome mà không ghi raw secret.” |
| “Không ai được truy cập trái phép.” | Không xác định quyền cụ thể | “Principal tenant A không được đọc, cập nhật hoặc xóa object thuộc tenant B qua các API và worker thuộc phạm vi.” |
| “Xử lý nhanh các CVE.” | Không có quy tắc ưu tiên | “Finding được phân loại và xử lý theo risk-tier, target và decision được công bố trong policy đang có hiệu lực.” |
| “Chống brute-force.” | Không có failure behavior | “Luồng xác thực phải giới hạn thử đoán credential theo principal và tín hiệu liên quan, có hành vi đã kiểm chứng với request vượt ngưỡng policy.” |
| “Xóa dữ liệu khi không cần.” | Không biết khi nào/kho nào | “Các record hết kỳ retention đã phê duyệt phải được xử lý trong các data stores thuộc inventory, có reconciliation và quản lý hold.” |
| “API không bao giờ lỗi.” | Không khả thi, không đo | “Khi policy decision không xác định được, thao tác xuất dữ liệu Restricted không được phát hành; sự kiện lỗi phải được ghi và chuyển xử lý.” |
| “Bật SAST.” | Công cụ, không biết chất lượng | “Mỗi thay đổi tại các thành phần thuộc scope phải được phân tích bởi SAST theo rule set đã phê duyệt; lỗi tool/skip không được báo PASS.” |
| “Quản lý secret an toàn.” | Không mô tả quyền và lifecycle | “Workload orders-api-prod chỉ được đọc secret thuộc scope của mình; khi credential bị revoke, hệ thống đích phải từ chối việc sử dụng theo policy.” |
| “Áp dụng zero trust.” | Slogan kiến trúc | “Mỗi kết nối service-to-service tới API được bảo vệ phải xác thực peer và kiểm tra authorization cho operation/resource, kể cả kết nối từ mạng nội bộ.” |
| “Có backup.” | Chưa nói recovery | “Bản sao dữ liệu thuộc phạm vi phải khôi phục được theo RPO/RTO đã phê duyệt và được kiểm chứng bằng restore test định kỳ.” |

Các ngưỡng và phiên bản trong bảng cần được **điền từ baseline, risk appetite hoặc quyết định có thẩm quyền**, không sao chép số liệu tùy ý.

### 6.1. Cách diễn đạt bắt buộc và tùy chọn

Trong đặc tả nội bộ, có thể thống nhất:

- **MUST / phải:** hành vi bắt buộc trong scope.
- **MUST NOT / không được:** hành vi cấm.
- **SHOULD / nên:** khuyến nghị có điều kiện; cần quy tắc xử lý khi không thực hiện.
- **MAY / có thể:** tùy chọn hoặc tính năng được phép.

Không trộn “phải hoặc nên” trong một câu. Nếu requirement bắt buộc, cần dùng động từ nhất quán; nếu chỉ là design option, ghi rõ là design note, tránh đưa vào kiểm thử bắt buộc.

## 7. Các nhóm security requirements cần biết

### 7.1. Security functional requirements

Mô tả hành vi cụ thể của hệ thống:

- Xác thực user/workload trước thao tác được bảo vệ.
- Kiểm tra authorization theo object và context.
- Không gửi dữ liệu sai tenant.
- Thu hồi session theo policy.
- Chặn upload vi phạm rule.
- Ghi event bảo mật cần thiết.
- Kiểm tra integrity của callback/webhook.

### 7.2. Security quality/nonfunctional requirements

Mô tả thuộc tính vận hành có thể đo:

- Tỷ lệ áp dụng control trên asset population xác định.
- Thời gian phản ứng với alert theo risk tier.
- Khả năng duy trì service khi dependency lỗi mà không fail-open.
- Availability và recovery objectives đã được duyệt.
- Tốc độ hoặc quy mô của security logging pipeline.
- Độ mới của evidence, credential và policy evaluation.

Đừng dùng từ “nonfunctional” để loại các yêu cầu này khỏi test. Chúng thường cần **load test, fault injection, review vận hành hoặc thử khôi phục**.

### 7.3. Security constraints

Ràng buộc giải pháp khi thực sự cần:

- Phải dùng approved cryptographic primitives theo baseline đang hiệu lực.
- Private signing key thuộc nhóm nhất định chỉ được sử dụng qua dịch vụ key management được chấp nhận.
- Các thay đổi production IAM phải đi qua change control có audit.
- Không sử dụng thư viện/phiên bản bị cấm theo chuẩn nội bộ.

Chúng vẫn cần **scope, source, owner và cách xác minh**.

### 7.4. Operational, procedural và evidence requirements

Không phải mọi nghĩa vụ nằm trong code:

- Access review phải có lịch, population, reviewer và quyết định.
- Incident detection phải có triage/escalation evidence.
- Key rotation phải được xác minh ở consumer.
- Backup restore phải có biên bản test và kết quả thực.
- Finding phải được sửa và retest trên deployment mục tiêu.
- Audit evidence phải được bảo vệ khỏi sửa đổi trái phép.

Những yêu cầu này cần owner vận hành và bằng chứng qua thời gian, không thể “PASS” chỉ bằng unit test.

### 7.5. Prevention, detection, response, recovery

| Control objective | Requirement mẫu | Verification |
| --- | --- | --- |
| **Preventive** | Request đọc dữ liệu khác tenant phải bị từ chối | Cross-tenant API/data tests |
| **Detective** | Hành động thay đổi quyền đặc quyền phải tạo event audit | Test event và review log pipeline |
| **Responsive** | Alert xác nhận compromise phải có workflow thu hồi token | Incident drill, token revoke verification |
| **Recovery** | Hệ thống phải phục hồi dữ liệu theo RPO/RTO áp dụng | Restore exercise, measured results |

Một chương trình assurance cần nhận diện những nhóm control **phù hợp rủi ro**, không chỉ yêu cầu “chặn” rồi bỏ qua detection/response/recovery.

## 8. Quy trình viết security requirement từ đầu đến cuối

### Bước 1. Xác định business context và phạm vi

Ghi hệ thống, sản phẩm, người dùng, vai trò, dữ liệu, data flows, môi trường, dependencies và mức độ quan trọng.

Đặt câu hỏi: “Ai sẽ dùng chức năng này, dữ liệu nào có thể bị lộ/sửa và hậu quả nghiệp vụ là gì?”

### Bước 2. Xác định assets và trust boundaries

Dùng DFD hoặc sơ đồ kiến trúc để nhận diện:

- Client và các entry points.
- Auth/identity provider.
- API/business service.
- Database, cache, queue, storage.
- External partner và internal worker.
- Admin/control-plane APIs.
- Luồng secret, key và audit.

Không để một boundary quan trọng biến mất vì sơ đồ quá đơn giản.

### Bước 3. Thu thập nghĩa vụ và security objectives

Kết hợp threat model với policy/standard và nghĩa vụ đã xác nhận. Ghi:

- Objective ID.
- Source ID/version.
- Risk hoặc threat liên quan.
- Owner xác nhận applicability.
- Deadline hoặc giai đoạn hiệu lực.

Nếu còn mâu thuẫn nguồn, đánh dấu **NEEDS_DECISION**, không tự chọn quy tắc nào có lợi cho triển khai.

### Bước 4. Viết misuse/abuse case

Ví dụ:

> User A có access token hợp lệ, biết ID đơn hàng B và gửi request GET hoặc export để vượt ranh giới tenant.

Một abuse case tốt nêu **attacker capability, precondition, target, action và expected impact**. Nó giúp tìm negative tests thay vì chỉ kiểm tra happy path.

### Bước 5. Phát biểu security requirement

Chỉ rõ **chủ thể thực thi, điều kiện, hành vi, scope và failure behavior**. Ví dụ:

> Orders API phải xác minh quyền đọc theo tenant của principal đã được xác thực và resource ownership tại thời điểm xử lý. Nếu quyền không hợp lệ hoặc không xác định được, API không được tiết lộ dữ liệu order qua response hoặc export.

Nếu việc kiểm tra phụ thuộc hệ thống policy có thể lỗi, thêm một requirement riêng về failure mode hoặc acceptance criterion liên quan.

### Bước 6. Phân tách và kiểm tra xung đột

Kiểm tra:

- Có nhiều hành vi không liên quan trong một câu?
- Có requirements trùng nhau nhưng khác tiêu chí?
- Có xung đột với quy trình nghiệp vụ hợp lệ?
- Có thể truy vết source?
- Có owner và đúng boundary?
- Có dùng thuật ngữ chưa định nghĩa?
- Có điều kiện ngoại lệ hoặc delegated authorization cần tách?

### Bước 7. Viết acceptance criteria trước triển khai

Viết cả:

- **Positive:** hành động hợp lệ vẫn thành công.
- **Negative:** hành động trái quyền bị từ chối.
- **Boundary:** role, tenant, token, TTL, lượng dữ liệu hoặc trạng thái ở rìa.
- **Failure:** dependency lỗi, context thiếu hoặc dữ liệu không hợp lệ.
- **Bypass:** các đường khác dùng cùng control.
- **Evidence:** phải có record nào để xác minh.

Một requirement **không có cách xác minh** cần được viết lại hoặc thiết kế phương pháp đánh giá phù hợp trước khi chấp thuận.

### Bước 8. Review đa chức năng và phê duyệt

Người tham gia tùy quy mô:

- Business/data owner xác nhận nghiệp vụ và phạm vi.
- Security/AppSec xác nhận threat và kiểm chứng.
- Engineering/architecture xác nhận tính khả thi và vị trí control.
- QA xác nhận test oracle.
- SRE/operations xác nhận các yêu cầu vận hành.
- Risk/legal/privacy xác nhận nghĩa vụ và residual risk khi liên quan.

Review không chỉ là sửa câu chữ: phải giải quyết **mâu thuẫn, thiếu phạm vi, mức ưu tiên và nguồn áp dụng**.

### Bước 9. Trace đến implementation, test và evidence

Mỗi requirement có link tới:

- Threat/risk/objective.
- Control/design.
- Owner.
- Code/configuration và deployment.
- Positive/negative tests.
- Test runs, audit records và evidence.
- Findings và remediation/retest.

### Bước 10. Duy trì khi hệ thống thay đổi

Khi thêm API, data field, tenant model, provider, identity flow hoặc control plane, cần đánh giá requirement bị ảnh hưởng. Một test cũ không tự đại diện cho build mới.

## 9. Sơ đồ traceability và chỗ dễ đứt chuỗi

~~~mermaid
flowchart TD
    A["Asset / Business process"] --> B["Threat scenario / Risk"]
    B --> C["Security objective"]
    D["Policy / Standard / Applicable obligation"] --> E["Security requirement"]
    C --> E
    E --> F["Control design / Owner"]
    F --> G["Implementation / Configuration"]
    E --> H["Acceptance criteria / Test cases"]
    G --> I["Test execution / Audit"]
    H --> I
    I --> J["Evidence + Build / Environment"]
    J --> K{"Meets requirement?"}
    K -- "Yes, sufficient evidence" --> L["Verified within scope"]
    K -- "No" --> M["Finding / Remediation / Retest"]
    K -- "Not enough evidence" --> N["Evidence gap / More assessment"]
    M --> I
    N --> I
~~~

Hai sai lầm phổ biến:

1. **Requirement không nối tới test:** thiết kế có vẻ đúng nhưng không ai chứng minh.
2. **Test không nối tới requirement/threat:** pipeline nhiều bài test nhưng không biết rủi ro quan trọng đã được bao phủ chưa.

Traceability không nhất thiết cần công cụ phức tạp. Một bảng ID có version và link tới evidence có thể đủ cho hệ thống nhỏ; tổ chức lớn có thể dùng requirements management system.

## 10. Case study xuyên suốt: viết requirements cho Orders API multi-tenant

### 10.1. Bối cảnh giả định

Một nền tảng thương mại điện tử cung cấp Orders API bằng **Java/Spring Boot** cho nhiều tổ chức khách hàng.

Thành phần:

- Browser/mobile client.
- Identity provider và API gateway.
- Orders API, authorization service, database.
- Cache, event bus, reporting/export worker.
- Payment/refund provider.
- Audit pipeline và security operations.

Dữ liệu: order ID, tenant ID, email liên hệ, địa chỉ giao hàng, tổng giá trị và trạng thái thanh toán.

Các user có thể là customer, support agent, tenant admin và platform operator. Mỗi role có phạm vi riêng. Đây là bối cảnh **minh họa**, không phải cấu hình production đã xác minh.

### 10.2. Threat model rút gọn

~~~mermaid
flowchart LR
    U["Customer / Support"] -->|"Request + Token"| GW["Gateway / Identity check"]
    GW --> API["Orders API"]
    API --> AUTHZ["Object / Tenant authorization"]
    AUTHZ --> DB[("Orders DB")]
    API --> CACHE[("Cache")]
    API --> OUT[("Event / Export Queue")]
    OUT --> WORKER["Report Worker"]
    WORKER --> STORAGE[("Private storage")]
    API --> AUDIT[("Protected audit")]
    WORKER --> AUDIT
    ATTACK["Actor tenant A"] -. "Tries resource B" .-> API
~~~

Các trust boundaries:

- **TB-01:** từ client không tin cậy tới API.
- **TB-02:** từ identity/session tới quyết định quyền trên object.
- **TB-03:** từ API tới database/cache.
- **TB-04:** từ API tới queue/worker và storage.
- **TB-05:** từ control plane/support role tới dữ liệu nhiều tenant.

### 10.3. Risk scenarios

| Threat ID | Kịch bản | Tác động |
| --- | --- | --- |
| **T-001** | Authenticated user đổi order ID của tenant khác | Tiết lộ dữ liệu khách hàng |
| **T-002** | Bulk export bỏ qua tenant filter | Rò dữ liệu số lượng lớn |
| **T-003** | Cache key thiếu tenant/permission | Cross-tenant response leakage |
| **T-004** | Report worker mất tenant context | Export sai tenant |
| **T-005** | Admin/support role không có ràng buộc case/scope | Truy cập vượt quyền |
| **T-006** | Trạng thái refund bị thay đổi đồng thời | Refund vượt tổng giá trị hợp lệ |
| **T-007** | Log ghi raw PII hoặc access token | Phơi lộ dữ liệu/credential |
| **T-008** | Audit event thiếu subject, outcome hoặc bị tắt | Không truy vết và phát hiện abuse |
| **T-009** | Secret database dùng chung nhiều môi trường | Vượt ranh giới dev/prod |
| **T-010** | Identity/policy dependency lỗi làm API fail-open | Bypass authorization |

### 10.4. Những security requirements đầu tiên

#### SEC-ORD-001 — Kiểm soát quyền đọc order theo tenant

**Requirement:**

> Mỗi thao tác đọc order qua API phải xác minh identity và chỉ truy xuất những order thuộc tenant mà principal có quyền tại thời điểm quyết định. Nếu principal không có quyền, tenant context không hợp lệ hoặc không xác định được quyền, API không được trả nội dung order đó.

**Acceptance criteria:**

- A đọc order A khi được cấp quyền → thành công.
- A đọc order B → không có dữ liệu B trong response.
- Token sai/thiếu identity → không đọc được order.
- Header/body tự khai tenant B không mở rộng quyền của A.
- Khi membership bị thu hồi, hành vi tuân theo revocation semantics đã phê duyệt.

**Verification:** API/integration tests; query authorization review; audit event sample.

**Evidence:** test ID, principal fixture, record ownership, actual response, policy/build version.

#### SEC-ORD-002 — Bảo vệ mọi đường export

**Requirement:**

> Mọi đường xuất order, bao gồm batch API và report worker trong phạm vi dịch vụ, phải áp dụng tenant/resource scope đã được xác minh và không được giao artifact chứa dữ liệu nằm ngoài quyền của requester.

**Acceptance criteria:**

- Export chỉ chứa các order được phép.
- Request mixed tenant không trả hoặc không tạo dữ liệu trái scope.
- Worker không tin tenant ID có thể bị giả mạo từ message.
- Retry và idempotency không làm mất context.
- Link tải artifact chỉ cho phép recipient đúng quyền theo policy.

**Verification:** end-to-end export test, queue tampering test, artifact-content assertion.

**Evidence:** export test run, generated synthetic file summary, worker audit.

#### SEC-ORD-003 — Cô lập cache

**Requirement:**

> Các cache entries chứa order data phải được phân vùng hoặc khóa theo tenant và các yếu tố permission có ảnh hưởng kết quả; thay đổi quyền phải được phản ánh thông qua invalidation hoặc reauthorization theo policy.

**Acceptance criteria:** cache warm bởi B không được làm A nhận dữ liệu B; quyền bị revoke không dẫn tới đọc qua cache cũ trái policy.

**Verification:** integration tests với cache thật, permission-change tests.

#### SEC-ORD-004 — Chuyển sang hành vi an toàn khi authorization không xác định

**Requirement:**

> Khi không xác minh được identity, tenant ownership hoặc authorization decision vì lỗi hoặc timeout, Orders API không được sử dụng tenant mặc định hoặc quyền rộng để tiếp tục các thao tác đọc, sửa hay xuất dữ liệu nhạy cảm.

**Acceptance criteria:** mock timeout/unavailable dependency, API deny/hold theo policy; không có artifact hoặc DB mutation trái quyền.

**Verification:** fault-injection integration test, error handling review.

#### SEC-ORD-005 — Kiểm soát refund theo trạng thái và số tiền

**Requirement:**

> Refund service phải bảo đảm tổng số tiền refund đã ghi nhận cho một order không vượt số tiền có thể hoàn và phải kiểm tra authorization, trạng thái order và approval có áp dụng trước khi commit thay đổi.

**Acceptance criteria:** request hợp lệ đạt; request vượt số tiền còn lại hoặc sai tenant bị từ chối; request đồng thời không phá invariant; retry không tạo refund trùng theo định nghĩa idempotency.

**Verification:** state-machine, concurrency, database constraint và integration tests.

#### SEC-ORD-006 — Không ghi raw secret vào log

**Requirement:**

> Các thành phần xử lý request, authentication và audit trong Orders API không được ghi access token, refresh token hoặc credential nguyên bản vào application logs, traces và error reports trong phạm vi vận hành đã xác định.

**Acceptance criteria:** test canary token và exception paths; không xuất hiện raw value ở log sinks; metadata cần thiết vẫn được audit.

**Verification:** logging/config review, canary scans, runtime log test.

#### SEC-ORD-007 — Audit các thao tác nhạy cảm

**Requirement:**

> Mọi thao tác thay đổi quyền, export order và refund thuộc phạm vi phải tạo event audit có actor/workload, action, resource scope, timestamp, outcome và correlation reference; audit không được ghi raw secret hoặc PII không cần thiết.

**Acceptance criteria:** event được tạo ở success, denial và failure theo semantics; event có thể liên kết giao dịch; không lưu payload nhạy cảm quá mức.

**Verification:** integration test và protected audit sample; review detection pipeline.

#### SEC-ORD-008 — Secret isolation giữa môi trường

**Requirement:**

> Workload production của Orders API chỉ được truy xuất database credential được phê duyệt cho production; staging và development identities không được đọc hoặc sử dụng production database credential.

**Acceptance criteria:** prod workload đọc đúng secret; staging identity đọc secret prod bị từ chối; audit ghi principal/action/outcome.

**Verification:** vault/IAM tests, config review.

### 10.5. Một yêu cầu thường cần nhiều tầng bảo vệ

SEC-ORD-001 là requirement về **hành vi bảo mật**, không chỉ “sử dụng tenant filter”. Implement có thể gồm:

- Verified principal và tenant membership.
- Object-level authorization.
- Tenant-scoped query.
- Database RLS nếu phù hợp.
- Cache phân vùng.
- Audit và monitoring.

Một database row policy có thể chặn query sai, nhưng requirement vẫn chưa đạt đầy đủ nếu API trả dữ liệu từ cache khác tenant.

## 11. Viết acceptance criteria bằng Gherkin

Gherkin giúp diễn đạt điều kiện quan sát được để business, developer, QA và security cùng review.

### 11.1. User đúng quyền

~~~gherkin
Feature: Tenant-scoped order access

  Scenario: Tenant A reads its own order
    Given principal A is authenticated
    And principal A is authorized for tenant A
    And order A belongs to tenant A
    When principal A requests order A
    Then the API returns only the authorized order A data
    And the response contains no information from tenant B
~~~

### 11.2. User sai tenant

~~~gherkin
Scenario: Tenant A cannot read tenant B's order
  Given principal A is authenticated for tenant A
  And order B belongs to tenant B
  When principal A requests order B by its valid identifier
  Then the API does not disclose order B data
  And the access decision is denied according to policy
  And the protected audit records the expected outcome
~~~

### 11.3. Policy decision không xác định

~~~gherkin
Scenario: Authorization service is unavailable
  Given principal A has a valid authentication session
  And the policy decision service cannot be reached
  When principal A requests export of Confidential orders
  Then the system does not release an export artifact
  And the failure is recorded without sensitive payload leakage
~~~

Gherkin là **đặc tả kiểm thử**; file scenario chưa được kết nối với step definitions và chưa chạy thì **không phải bằng chứng PASS**.

### 11.4. Đừng biến Given thành giả định không được kiểm chứng

Nếu test chỉ viết “Given user A is authorized” bằng mock, nó không chứng minh authorization implementation thực. Test cần phân biệt:

- **Unit:** kiểm tra logic với fixture/mocks.
- **Integration:** kiểm tra policy và repository/các thành phần phối hợp.
- **End-to-end:** kiểm tra identity/tenant và API thực, có cấu hình môi trường cụ thể.

Nếu claim bao gồm IAM policy hoặc database RLS, cần thêm test/inspection ở những lớp đó.

## 12. Java/Spring Boot: biến requirement thành code và test

### 12.1. Anti-pattern

Một service chỉ tìm order theo ID:

~~~java
public OrderView getOrder(UUID orderId) {
    return repository.findById(orderId)
            .map(OrderView::from)
            .orElseThrow(ResourceNotFoundException::new);
}
~~~

Nếu user đã đăng nhập nhưng service không kiểm tra resource ownership, kẻ tấn công có thể gửi một order ID thuộc người khác. UUID khó đoán **không phải** authorization boundary.

### 12.2. Thiết kế tenant-scoped service

Mã dưới đây là **ví dụ Java rút gọn** để biểu diễn requirement. Các domain types và cấu hình Spring Security cần được triển khai đầy đủ trong dự án thực.

~~~java
public record VerifiedPrincipal(
        String subjectId,
        UUID tenantId) {
}

public interface OrderRepository {
    Optional<Order> findByIdAndTenantId(UUID id, UUID tenantId);
}

public record Order(UUID id, UUID tenantId, String status) {
}

public record OrderView(UUID id, String status) {
    static OrderView from(Order order) {
        return new OrderView(order.id(), order.status());
    }
}

public final class ResourceNotFoundException extends RuntimeException {
}

@Service
public class OrderQueryService {
    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    public OrderView getOrder(UUID id, VerifiedPrincipal principal) {
        // Caller must come from trusted authentication and membership.
        Order order = orders
                .findByIdAndTenantId(id, principal.tenantId())
                .orElseThrow(ResourceNotFoundException::new);

        return OrderView.from(order);
    }
}
~~~

Những điểm bắt buộc kiểm chứng **ngoài mã này**:

- VerifiedPrincipal do authentication provider đáng tin xây dựng, không deserialize từ request body.
- Tenant membership được kiểm tra theo chính sách hiện hành.
- Repository thật có tenant filter đúng và không tạo bypass qua custom query.
- Các operation update/delete/export cũng áp quyền.
- Cache, workers và admin paths không bỏ qua boundary.
- Việc trả 404 thay 403 cần nhất quán, không lộ sự tồn tại của object qua response, timing hoặc dữ liệu khác.
- Audit có actor, action và outcome theo policy.

### 12.3. Unit test phản ánh hai acceptance criteria

~~~java
@ExtendWith(MockitoExtension.class)
class OrderQueryServiceSecurityTest {
    @Mock
    OrderRepository repository;

    @InjectMocks
    OrderQueryService service;

    private final UUID tenantA = UUID.randomUUID();
    private final UUID tenantB = UUID.randomUUID();
    private final UUID orderId = UUID.randomUUID();

    @Test
    void ownTenantOrder_isReadable() {
        VerifiedPrincipal caller = new VerifiedPrincipal("user-a", tenantA);
        Order order = new Order(orderId, tenantA, "PAID");

        when(repository.findByIdAndTenantId(orderId, tenantA))
                .thenReturn(Optional.of(order));

        OrderView view = service.getOrder(orderId, caller);

        assertEquals(orderId, view.id());
        verify(repository).findByIdAndTenantId(orderId, tenantA);
    }

    @Test
    void otherTenantOrder_isNotDisclosed() {
        VerifiedPrincipal caller = new VerifiedPrincipal("user-a", tenantA);

        when(repository.findByIdAndTenantId(orderId, tenantA))
                .thenReturn(Optional.empty());

        assertThrows(
                ResourceNotFoundException.class,
                () -> service.getOrder(orderId, caller));

        verify(repository).findByIdAndTenantId(orderId, tenantA);
        verifyNoMoreInteractions(repository);
    }
}
~~~

**Giới hạn evidence:** unit tests dùng mock repository, nên chỉ chứng minh service gọi phương thức được đặt tên tenant-scoped trong các tình huống đã cấu hình. Chúng **không chứng minh query SQL thực tế đã lọc tenant**, không chứng minh token thật được kiểm tra, và không kiểm tra cross-tenant access qua worker/cached data.

Với claim SEC-ORD-001, nên bổ sung **integration tests với database thật hoặc tương đương**, API security tests và negative tests trên những entry points khác trong scope.

### 12.4. Requirement không phải chứng minh implementation đã an toàn

Một tài liệu requirements hoàn chỉnh là **thiết kế tiêu chí**; code sample là **hướng triển khai**; test code có sẵn là **khả năng kiểm thử**. Chỉ **test run và bằng chứng được review** trên môi trường cụ thể mới có thể hỗ trợ kết luận implementation đáp ứng yêu cầu.

## 13. Ví dụ requirement cho các lĩnh vực bảo mật khác

Các phát biểu sau là **mẫu minh họa**. Những ngưỡng thời gian, phân loại dữ liệu và baseline được nói đến phải do tổ chức xác nhận theo rủi ro và nghĩa vụ thực tế.

### 13.1. Authentication và session

**SEC-AUTHN-001:**

> API được bảo vệ phải chỉ chấp nhận access token sau khi xác minh signature hoặc cơ chế proof tương ứng, issuer, audience, thời hạn và các claims bắt buộc theo chính sách xác thực hiện hành; token thiếu hoặc không hợp lệ phải bị từ chối.

**Test:** token đúng/sai signature, wrong audience, expired, malformed, thiếu claim và token dùng cho dịch vụ khác.

**SEC-SESS-001:**

> Sau hành động thu hồi session được policy định nghĩa, các thao tác tiếp theo sử dụng session/token đã bị vô hiệu phải bị từ chối tại các resource servers trong phạm vi theo thời gian hiệu lực đã được phê duyệt.

**Test:** revoke rồi dùng lại session, kiểm tra gateway/cache/resource server; ghi mức trễ nếu có.

Nếu access token là self-contained và không có revoke tức thì, phải thiết kế semantics rõ (TTL ngắn, denylist/introspection hoặc biện pháp khác) thay vì viết “thu hồi ngay” mà không thể thực thi.

### 13.2. Authorization và privileged access

**SEC-AUTHZ-001:**

> Mỗi thao tác cập nhật thông tin khách hàng phải kiểm tra actor được xác minh có quyền trên customer record và action đó; quyền admin/role tổng quát không được tự suy thành quyền với mọi tenant trừ khi có scope đặc biệt được phê duyệt.

**Test:** owner, non-owner, wrong tenant, privileged support theo case, bulk update và delegated access.

**SEC-PRIV-001:**

> Mọi hành động cấp quyền đặc quyền trong production phải có actor được xác thực, approval theo thẩm quyền, audit event và phạm vi/quyền được ghi trước khi có hiệu lực.

**Test:** self-approval không hợp lệ, privilege escalation, approver sai, audit failure và expiry của quyền tạm.

### 13.3. Input, file và output

**SEC-INPUT-001:**

> Các giá trị do client cung cấp để lọc/search trong database phải được xử lý tách biệt khỏi cú pháp truy vấn bằng cơ chế truy vấn an toàn được baseline phê duyệt; input không hợp lệ không được làm thay đổi cấu trúc câu lệnh thực thi.

**Test:** code review parameter binding, inputs đặc biệt và integration tests.

**SEC-UPLOAD-001:**

> File upload chỉ được chấp nhận với loại, kích thước và cấu trúc được allowlist cho use case; file không hợp lệ phải bị từ chối hoặc cách ly trước khi trở nên truy cập công khai.

**Test:** file sai type/magic bytes, oversized, malformed, double extension, archive edge cases và storage ACL.

**SEC-OUTPUT-001:**

> Dữ liệu người dùng được hiển thị trong HTML phải được encode phù hợp context output và không được đưa thành executable script ngoài các trường hợp được cho phép, kiểm soát rõ.

**Test:** output context, DOM behavior, template rendering và XSS regression.

### 13.4. Cryptography và key management

**SEC-CRYPTO-001:**

> Các kết nối từ client đến API truyền dữ liệu nhạy cảm phải sử dụng transport protection theo phiên bản baseline mật mã đã được phê duyệt; kết nối không đáp ứng baseline không được xử lý dữ liệu đó.

**Test:** TLS/protocol/certificate configuration và runtime negotiation theo phạm vi.

**SEC-KEY-001:**

> Private key thuộc nhóm signing keys của service phải được quản lý với quyền sử dụng riêng cho signing identity; việc xuất key material bản rõ ngoài boundary được phê duyệt phải bị ngăn hoặc xử lý theo chính sách và được audit.

**Test:** IAM negative tests, signing audit, key export policy và revoke/rotation exercise.

### 13.5. Secret management

**SEC-SECRET-001:**

> Credential production dùng bởi workload phải được lấy từ cơ chế secret distribution được phê duyệt và không được đưa nguyên bản vào source code, container image hoặc log; mỗi workload chỉ được lấy secrets trong scope được cấp.

**Test:** repo/image/log scanning, cross-workload negative access, runtime configuration.

**SEC-SECRET-002:**

> Sau khi một credential bị thu hồi theo quy trình compromise, việc xác thực mới bằng credential cũ phải bị từ chối tại hệ thống đích; các session hoặc cache còn hiệu lực phải được xử lý theo revoke policy đã xác nhận.

**Test:** revoke rồi gọi resource, kiểm tra session, pool, cache và audit.

### 13.6. Audit và detection

**SEC-AUDIT-001:**

> Các thao tác cấp quyền, xuất dữ liệu Confidential và thay đổi security policy phải tạo audit event chứa actor/workload, action, resource scope, outcome và timestamp; event không được chứa access token hoặc secret nguyên bản.

**Test:** positive/negative/timeout cases, audit ingestion, redaction và access review.

**SEC-DETECT-001:**

> Detection pipeline phải tạo signal và route tới người/nhóm chịu trách nhiệm khi nhận được event thuộc danh mục suspicious privileged changes đã phê duyệt; việc không thể gửi signal phải được phát hiện và vận hành theo quy trình.

**Test:** synthetic security event và drill trong scope, xác minh alert/triage/acknowledgment.

### 13.7. Data protection và privacy

**SEC-DATA-001:**

> Export dữ liệu nhãn Confidential phải kiểm tra authorization, destination và mục đích chia sẻ theo policy đang áp dụng trước khi cấp artifact hoặc download access.

**Test:** approved/disallowed destination, wrong tenant, data classification tampering và policy timeout.

**SEC-PRIVACY-001:**

> Với các hoạt động xử lý mà privacy owner đã xác nhận phải dựa trên consent, hệ thống phải kiểm tra trạng thái consent hợp lệ cho đúng purpose tại điểm quyết định, và thực thi withdrawal semantics đã được phê duyệt.

**Test:** no consent, wrong purpose, revoked consent, queue delay, retry và provider dispatch.

Không mặc định mọi xử lý dữ liệu cá nhân đều dựa trên consent hoặc có cùng nghĩa vụ ở mọi khu vực.

### 13.8. Availability, backup và recovery

**SEC-AVAIL-001:**

> Một tenant không được vượt giới hạn tiêu thụ tài nguyên thuộc phạm vi dịch vụ đã được phân bổ theo tier chính sách; hoạt động quá giới hạn phải được xử lý sao cho không làm vượt ngưỡng tác động tới các tenant khác được đặt ra trong capacity test.

**Test:** rate/quota, load/fairness và resource exhaustion dưới điều kiện được phép.

**SEC-RECOVERY-001:**

> Các dữ liệu quan trọng thuộc inventory phải có cơ chế backup và restore được kiểm tra theo RPO/RTO đã phê duyệt cho hệ thống; bản restore phải giữ đúng ranh giới quyền, trạng thái dữ liệu và integrity theo tiêu chí kiểm tra.

**Test:** restore exercise, measured RPO/RTO, authorization và consistency after restore.

### 13.9. Software supply chain và Secure Development

**SEC-SDLC-001:**

> Các thay đổi vào nhánh phát hành của những service thuộc risk tier đã xác định phải hoàn tất các security checks bắt buộc trước release; kết quả scanner/test bị lỗi, không chạy hoặc bị skip không được đánh dấu PASS.

**Test:** CI pipeline positive/negative gate, missing scanner, tool timeout, approval flow.

**SEC-SUPPLY-001:**

> Mỗi artifact triển khai vào production phải có provenance/identity metadata đủ để liên kết với commit, build pipeline và các security checks đã phê duyệt; artifact không khớp record phát hành không được tự động coi là đã kiểm thử.

**Test:** deploy artifact digest vs build record, signature/provenance checks theo baseline.

## 14. Đặt ngưỡng định lượng một cách có căn cứ

### 14.1. “Measurable” không có nghĩa tự chọn số đẹp

Một requirement “incident alert phải được xử lý trong 5 phút” có thể kiểm tra được về hình thức, nhưng chưa chắc là mục tiêu đúng. Chọn ngưỡng cần xét:

- Data class, business impact và threat scenario.
- Tốc độ attacker có thể gây hại.
- Capability và staffing vận hành.
- Kỳ vọng của risk owner.
- Nghĩa vụ hoặc SLA có áp dụng.
- Đo thử baseline và khả năng đạt.
- Phương pháp đo và bằng chứng.

**Ví dụ hoàn toàn giả định:** đối với alert nghi lộ production signing key, tổ chức quyết định mục tiêu chuyển cấp tới on-call trong **15 phút** kể từ lúc detection pipeline xác nhận alert. Đây không phải mức chuẩn phổ quát; muốn đưa thành requirement thật phải có phê duyệt và risk rationale.

### 14.2. Mẫu cho requirement định lượng

> Trong [population và thời gian], [service/team] phải đạt [chỉ số với đơn vị, phép đo, mẫu số và ngưỡng] đối với [event/asset], sử dụng [phương pháp kiểm chứng] và [hành vi khi không đạt].

Ví dụ:

> Trong mỗi kỳ review được xác định, nhóm quản lý secret phải xác minh rotation và revoke theo policy đối với toàn bộ credential thuộc danh sách critical đang hiệu lực; mỗi kết quả cần có secret reference, owner, version và bằng chứng credential cũ không còn được dùng cho xác thực mới.

Nếu policy quy định một tỷ lệ hoặc thời gian cụ thể, nêu rõ denominator, kỳ và exceptions. Không dùng một metric chung “100% secure”.

### 14.3. Chú ý percentile và measurement window

Khi requirement phụ thuộc latency hoặc throughput:

- Tính trên request population nào?
- P95/P99 hay mean?
- Cửa sổ 1 giờ, 24 giờ hay 30 ngày?
- Khi dependency bị lỗi, có tính request thất bại?
- Phân tách endpoint rủi ro cao hay tổng hệ thống?
- Có loại trừ maintenance window theo policy?
- Evidence được lấy từ nguồn tin cậy nào?

Một chỉ số không có denominator và phạm vi có thể bị hiểu hoặc tối ưu sai.

## 15. Xử lý failure behavior, ngoại lệ và điều kiện biên

### 15.1. Failure mode là phần của requirement

Không chỉ viết hệ thống phải làm gì khi mọi thứ bình thường. Cần hỏi:

- Identity provider unavailable thì sao?
- Policy engine timeout thì sao?
- Không xác định được tenant/owner?
- Secret manager không trả credential?
- Audit sink không nhận event?
- Queue nhận event trùng hoặc trễ?
- File scanner không đọc được?
- Database transaction rollback sau khi external API đã gọi?

Với thao tác rủi ro cao, có thể yêu cầu **deny/hold** thay vì cho đi tiếp khi thiếu quyết định. Với dịch vụ có nhu cầu khả dụng đặc biệt, cần degraded mode được thiết kế và phê duyệt, **không tự fail-open**.

### 15.2. Ngoại lệ phải minh bạch

Ví dụ một integration legacy chưa hỗ trợ workload identity. Có thể có ngoại lệ có thời hạn với compensating controls, nhưng yêu cầu chính vẫn nên được ghi và quản lý.

Ngoại lệ cần:

- Requirement ID và phạm vi không đáp ứng.
- Lý do, threat/risk và impact.
- Chủ thể chấp nhận rủi ro đúng thẩm quyền.
- Control bù trừ và bằng chứng.
- Thời hạn, trigger review và kế hoạch xử lý.
- Quy định rõ những nghĩa vụ bắt buộc không được miễn trừ nội bộ.

**Approved exception ≠ Verified requirement.**

### 15.3. Requirement có mâu thuẫn

Ví dụ:

- SEC-LOG: ghi mọi request body để điều tra.
- SEC-PRIVACY: không thu thập thông tin cá nhân không cần thiết trong log.

Cần giải quyết ở cấp requirement:

> Các security events phải được ghi đủ metadata phục vụ truy vết, đồng thời không được chứa raw secret và các trường dữ liệu cá nhân không cần thiết.

Sau đó tách rõ event schema, allowed fields, access, retention và test. Không để hai đội tự xử lý xung đột bằng cấu hình trái nhau.

## 16. Quản lý security requirements như một artifact có vòng đời

### 16.1. Trạng thái điển hình

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> REVIEWED: Business/Security/Engineering review
    REVIEWED --> APPROVED: Authorized approval
    APPROVED --> IMPLEMENTED: Control deployed in scope
    IMPLEMENTED --> VERIFIED: Tests and evidence reviewed
    VERIFIED --> REASSESS: Material change / new threat
    REASSESS --> REVIEWED: Requirement revised or reconfirmed
    REVIEWED --> DRAFT: Needs clarification
    APPROVED --> SUPERSEDED: Replaced with versioned requirement
    VERIFIED --> SUPERSEDED: Replaced with versioned requirement
    SUPERSEDED --> [*]
~~~

**Approved** không đồng nghĩa **Implemented**; **Implemented** không đồng nghĩa **Verified**. Ngoại lệ và finding nên có record riêng thay vì thay status thành “PASS”.

### 16.2. Versioning và change control

Khi đổi security requirement, cần ghi:

- ID ổn định và version.
- Nội dung trước/sau.
- Lý do đổi (threat mới, policy, product, architecture, regulation).
- Phạm vi hệ thống và consumers bị ảnh hưởng.
- Phân tích tác động lên controls/tests/evidence.
- Owner và approver.
- Effective date/transition.
- Kế hoạch migrate/retest và xử lý requirement cũ.

Đừng âm thầm nới từ “must” thành “should” để làm pipeline xanh. Mọi thay đổi làm giảm mức bảo vệ phải được đánh giá rủi ro và phê duyệt theo policy.

### 16.3. Khi nào cần revalidate?

- Thêm endpoint hoặc business flow mới.
- Đổi tenant, role, permission hoặc identity provider.
- Đổi database/cache/search/queue.
- Chuyển deployment environment hoặc cloud account.
- Thêm vendor, dữ liệu hoặc mục đích xử lý mới.
- Cập nhật crypto baseline, key management hoặc network policy.
- Phát hiện incident, pentest finding hoặc CVE ảnh hưởng threat.
- Thay đổi luật/hợp đồng đã được xác nhận áp dụng.
- Đổi control owner hoặc risk owner.
- Control trở nên không còn khả thi hoặc quá hạn.

Evidence cũ có thể vẫn hữu ích làm lịch sử nhưng không tự chứng minh requirement trên **artifact/architecture mới**.

## 17. Requirements traceability matrix (RTM)

Một **RTM** kết nối các nguồn và bằng chứng để phát hiện gaps.

| Req ID | Risk/threat | Control owner | Verification method | Evidence status | Assessment |
| --- | --- | --- | --- | --- | --- |
| SEC-ORD-001 | T-001 cross-tenant read | Orders API owner | API + DB integration tests | Planned | Not verified |
| SEC-ORD-002 | T-002/T-004 export/worker | Reporting owner | E2E export, worker negative tests | Planned | Not verified |
| SEC-ORD-003 | T-003 cache leak | Platform owner | Cache integration tests | Planned | Not verified |
| SEC-ORD-004 | T-010 fail-open | Orders API owner | Policy timeout/fault injection | Planned | Not verified |
| SEC-ORD-005 | T-006 refund race | Payments owner | Concurrency/state tests | Planned | Not verified |
| SEC-ORD-006 | T-007 secret leakage | SRE/App owner | Canary log scan | Planned | Not verified |
| SEC-ORD-007 | T-008 audit gaps | Security operations | Audit integration + sampled events | Planned | Not verified |
| SEC-ORD-008 | T-009 credential boundary | IAM/Platform owner | Vault negative access | Planned | Not verified |

**RTM trên là kế hoạch minh họa, không phải báo cáo PASS.** Trạng thái “Planned” có nghĩa chưa có bằng chứng thực thi.

### 17.1. Gaps mà RTM giúp tìm

- Một threat quan trọng **không có requirement**.
- Requirement đã phê duyệt **không có control owner**.
- Control đã triển khai nhưng **không có test**.
- Test tồn tại nhưng **không gắn build/environment**.
- Finding đã đóng bằng PR nhưng **không có retest**.
- Requirement từ chuẩn bên ngoài **đã đổi phiên bản** nhưng mapping chưa cập nhật.
- Một control dùng chung thay đổi nhưng dependent services **chưa được đánh giá lại**.

### 17.2. Coverage không phải effectiveness

Giả sử có 20 requirements được xác nhận áp dụng, 15 có test và evidence đã review, 3 chưa test và 2 có evidence không đạt.

- **Verified evidence coverage** theo định nghĩa mẫu = 15/20 = **75%**.
- Điều này **không có nghĩa hệ thống an toàn 75%**.
- Hai requirement không đạt có thể liên quan dữ liệu nhạy cảm nhất.
- Ba requirement chưa test là **unknown**, không được tính như PASS.
- Cần phân loại mức rủi ro và impact thay vì lấy trung bình các yêu cầu khác bản chất.

## 18. Từ requirement tới assessment evidence

### 18.1. Ba lớp cần xác minh

| Lớp | Câu hỏi | Evidence |
| --- | --- | --- |
| **Design effectiveness** | Requirement có giải quyết đúng threat và control design có hợp lý? | DFD, threat model, requirement review, architecture decision |
| **Implementation effectiveness** | Code/config có thực thi đúng requirement? | Code/config review, unit/integration/API tests, policy-as-code |
| **Operating effectiveness** | Control có hoạt động trong môi trường/kỳ thực? | Runtime audit, control health, access review, drill, periodic tests |

Một requirement “audit mọi refund” cần không chỉ code có lệnh ghi log mà còn xác minh event đến nơi lưu/giám sát đúng trong phạm vi vận hành.

### 18.2. Test evidence nên ghi gì?

- Requirement/test IDs, phiên bản và tiêu chí đạt.
- Asset, service, environment và build/artifact digest.
- Test data fixture (ưu tiên synthetic), principal/role và resource scope.
- Precondition, action, expected và actual result.
- Thời gian, tool/test runner/version và reviewer.
- Reference tới log, report hoặc audit record được bảo vệ.
- Các giả định, excluded paths, skip và limitations.
- Finding, remediation và retest khi có lỗi.
- Tính toàn vẹn, quyền xem và thời hạn evidence.

**Không lưu raw production secret hoặc PII trong hồ sơ kiểm thử** nếu có thể dùng reference, redaction hoặc synthetic data.

### 18.3. Kết luận có giới hạn

Dùng những kết luận khác nhau:

- **Verified/effective within scope:** bằng chứng đủ cho tiêu chí trong phạm vi đã đánh giá.
- **Partially verified:** một số đường hoặc lớp đạt nhưng thiếu coverage.
- **Not met/ineffective:** có bằng chứng control không đáp ứng requirement.
- **Insufficient evidence:** chưa có cơ sở kết luận.
- **Exception accepted:** risk owner chấp nhận rủi ro theo thẩm quyền; không xem là đạt.
- **Not applicable:** xác nhận có căn cứ không áp dụng.

Một test chạy ở integration với mock service không tự cho phép kết luận production đã đáp ứng requirement.

## 19. Mẫu hồ sơ requirement có cấu trúc

YAML dưới đây là **mẫu minh họa cho SEC-ORD-001**, không khẳng định hệ thống thực đã được kiểm chứng.

~~~yaml
requirement_id: "SEC-ORD-001"
version: "1.0"
title: "Tenant-scoped order access"
module: "SECURITY_SECURITY_ASSURANCE"
status: "DRAFT"
type: "SECURITY_FUNCTIONAL"
priority: "HIGH_DEMO"
source:
  threat_ids:
    - "T-001"
  risk_id: "RISK-CROSS-TENANT-READ-DEMO"
  policy_ref: "POL-DATA-ACCESS-DEMO"
scope:
  service: "orders-api"
  environment:
    - "integration"
    - "production"
  operations:
    - "read-order"
  data_class: "CONFIDENTIAL_DEMO"
  actors:
    - "authenticated-customer"
    - "authorized-support"
statement: >-
  Each order read must verify that the requesting principal has
  permission for the resource within a trusted tenant context.
  Unauthorized or indeterminate access must not disclose order data.
rationale: "Prevent unauthorized cross-tenant disclosure"
acceptance_criteria:
  - id: "AC-01"
    case: "authorized principal reads its own order"
    expected: "ALLOW"
  - id: "AC-02"
    case: "tenant A principal requests tenant B order"
    expected: "NO_DISCLOSURE"
  - id: "AC-03"
    case: "principal sends untrusted tenant B header"
    expected: "NO_PRIVILEGE_EXPANSION"
  - id: "AC-04"
    case: "policy decision unavailable"
    expected: "NO_UNAUTHORIZED_DATA_RELEASE"
control_owner: "Orders API Technical Owner"
risk_owner: "Orders Product Risk Owner"
verification:
  planned_methods:
    - "api-negative-authorization-test"
    - "database-integration-test"
    - "security-configuration-review"
  test_refs: []
  evidence_refs: []
  result: "NOT_VERIFIED"
exceptions: []
review:
  business_approval: "PENDING"
  security_approval: "PENDING"
  next_action: "Review scope and execute acceptance tests"
~~~

Đây là schema gợi ý, **không phải tiêu chuẩn máy đọc bắt buộc**. Trong thực tế có thể lưu bằng backlog/story, requirement database hoặc policy-as-code nếu giữ được ID, version, owner và traceability.

### 19.1. Nhận biết một requirement còn “Draft”

Nếu chưa có:

- Scope có trách nhiệm rõ.
- Nguồn/rationale và applicability.
- Security property và failure behavior.
- Acceptance criteria và phương pháp test.
- Owner, priority và cơ chế approval.

Thì không nên báo requirement đã đủ để triển khai hoặc đủ bằng chứng compliance.

## 20. Vai trò và RACI khi viết security requirements

| Vai trò | Trách nhiệm chính | Điều không nên tự suy |
| --- | --- | --- |
| **Product/business owner** | Mục đích, business flow, tác động nghiệp vụ | Business requirement tự bao phủ threat |
| **Security architect/AppSec** | Threat analysis, security claims và review tiêu chí | Có review thiết kế là production an toàn |
| **Engineering/application owner** | Khả thi, ranh giới thực thi, triển khai control | Có code là đã đạt acceptance |
| **QA/security testing** | Test design, positive/negative/bypass và evidence | Mọi 403 là đúng authorization |
| **SRE/platform** | Runtime, availability, logging, deployment và vận hành | CI PASS tương đương runtime |
| **Data/privacy owner** | Data class, purpose, retention và yêu cầu liên quan | Một mẫu consent áp dụng mọi nơi |
| **Risk owner** | Ưu tiên, treatment, residual risk trong thẩm quyền | Có thể miễn yêu cầu bắt buộc trái quy tắc |
| **Assurance/auditor** | Đánh giá traceability và chất lượng bằng chứng | Tự chịu trách nhiệm viết code sửa lỗi |
| **Legal/compliance** | Xác nhận nghĩa vụ thực tế áp dụng | Có policy là control đã triển khai |

RACI minh họa (*R = thực hiện; A = chịu trách nhiệm cuối cùng; C = tham vấn; I = thông báo*):

| Hoạt động | Business owner | AppSec | Engineering | QA | Risk owner | Assurance |
| --- | --- | --- | --- | --- | --- | --- |
| Xác định nghiệp vụ, assets, data scope | **A/R** | C | C | C | C | I |
| Threat-to-requirement mapping | C | **A/R** | C | C | C | C |
| Viết acceptance criteria | C | **A** | R | R | I | C |
| Approve requirement trong phạm vi | C | **A/R** | C | C | C | C |
| Implement control | I | C | **A/R** | C | I | C |
| Chạy test và lưu evidence | I | C | R | **A/R** | I | C |
| Review assurance evidence | I | C | C | C | I | **A/R** |
| Accept residual risk đúng quyền | C | C | C | I | **A/R** | I |
| Retest và đóng finding | I | C | R | **A/R** | C | C |

Tổ chức thực phải phân công cụ thể. Nếu risk owner đồng thời duyệt change và xác minh evidence, có thể cần review độc lập theo mức rủi ro.

## 21. Chỉ số quản lý chất lượng requirements

| Chỉ số | Hỗ trợ quyết định | Giới hạn |
| --- | --- | --- |
| **Source traceability coverage** | Bao nhiêu requirements có nguồn risk/policy/obligation | Có link không chứng minh nguồn áp đúng |
| **Threat-to-requirement coverage** | Threats đáng kể đã có requirement xử lý | Threat model có thể chưa đầy đủ |
| **Requirement atomicity/ambiguity findings** | Số yêu cầu cần viết lại | Cần review thực chất, không chỉ đếm câu |
| **Acceptance criterion completeness** | Requirement có positive, negative, failure tests phù hợp | Có criteria không có nghĩa đã chạy |
| **Owner assignment coverage** | Requirement có người chịu trách nhiệm | Tên owner không bảo đảm thực thi |
| **Verification evidence coverage** | Yêu cầu có evidence đã review | Evidence có thể sai build/scope |
| **Unverified critical requirements** | Những yêu cầu rủi ro cao chưa được kiểm chứng | Cần ưu tiên theo impact |
| **Requirements changed after approval** | Độ biến động và yêu cầu retest | Nhiều thay đổi không tự xấu |
| **Superseded mappings unresolved** | Ref/test còn gắn version cũ | Cần kiểm tra dependency |
| **Exception age/expiry** | Ngoại lệ quá hạn và residual risk | Exception không phải PASS |
| **Finding recurrence** | Lỗi requirement/design/test tái diễn | Cần phân tích root cause |
| **Time from requirement to verified evidence** | Khả năng hoàn tất assurance lifecycle | Không tối ưu tốc độ bằng cách giảm test |

Chỉ số nên giúp xác định **công việc chưa được chứng minh**. Đừng “nâng điểm” bằng cách xóa requirements khó hoặc đổi status từ Blocked thành Completed mà không có evidence.

## 22. Các sai lầm thường gặp khi viết security requirement

### 22.1. Viết khẩu hiệu thay vì hành vi

**Sai:** “Phải theo zero trust và best practices.”

**Sửa:** xác định identity, trust boundary, quyền, resource và negative tests cụ thể.

### 22.2. Chỉ nêu giải pháp

**Sai:** “Dùng WAF để chống tất cả tấn công.”

**Sửa:** xác định threat và security properties; WAF có thể là control bổ sung, không thay validation hoặc authorization.

### 22.3. Nhồi nhiều yêu cầu vào một câu

**Sai:** “Ứng dụng phải xác thực, phân quyền, mã hóa, log, backup, revoke và cảnh báo mọi trường hợp.”

**Sửa:** phân tách requirements có owner, scope và verification riêng, ghi dependency.

### 22.4. Không viết negative behavior

**Sai:** “User xem order của mình được.”

**Sửa:** thêm “user không được xem order tenant khác dù biết ID; lỗi policy không fail-open”.

### 22.5. Không định nghĩa ai có quyền

**Sai:** “Admin được đọc dữ liệu.”

**Sửa:** định nghĩa admin loại nào, tenant nào, action nào, có support case/approval hay không.

### 22.6. Không xét async, cache và alternate paths

**Sai:** chỉ viết requirement cho một controller.

**Sửa:** scope cả export, worker, cache và admin API có liên quan hoặc ghi requirement con riêng.

### 22.7. Đặt số tùy ý

**Sai:** “Mọi critical incident xử lý trong 1 phút” mà không có đánh giá/phê duyệt.

**Sửa:** có risk rationale, nguồn target, window và phương pháp đo.

### 22.8. Không xác định hành vi khi dependency lỗi

**Sai:** “Nếu policy engine lỗi thì bỏ qua để đảm bảo availability.”

**Sửa:** định nghĩa failure behavior dựa trên data class, risk và quyền có thẩm quyền, không vô tình cấp quyền.

### 22.9. Nhầm requirement “Approved” với control “Verified”

**Sai:** tài liệu có chữ ký thì báo compliance đạt.

**Sửa:** giữ trạng thái design/implementation/operating và evidence riêng.

### 22.10. Bỏ ngữ cảnh pháp lý và dữ liệu

**Sai:** áp cùng yêu cầu cho mọi mục đích và jurisdiction.

**Sửa:** để legal/privacy owner xác nhận applicability và version trước khi đưa vào phạm vi bắt buộc.

### 22.11. Đóng requirement khi test bị skip

**Sai:** pipeline xanh do không chạy DAST/API negative test.

**Sửa:** phân biệt PASS, FAIL, NOT RUN, BLOCKED và INSUFFICIENT EVIDENCE.

### 22.12. Thay đổi requirement mà không cập nhật test

**Sai:** chuyển từ single tenant sang multi-tenant, giữ test cũ.

**Sửa:** impact analysis, reapproval, bổ sung cross-tenant cases và retest.

### 22.13. Dùng exception để biến thất bại thành đạt

**Sai:** thiếu MFA được chấp nhận rủi ro rồi report requirement PASS.

**Sửa:** giữ gap/exception/residual risk minh bạch theo thẩm quyền.

### 22.14. Yêu cầu không có người chịu trách nhiệm

**Sai:** “Tổ chức phải quản lý secret” nhưng không biết ai rotate, revoke và xác minh.

**Sửa:** gán control owner, consumer, risk owner, verification owner và mốc review.

## 23. Checklist kiểm tra một security requirement trước khi phê duyệt

- [ ] Có ID ổn định, version và tiêu đề rõ.
- [ ] Có source/rationale từ threat, risk, policy hoặc nghĩa vụ đã xác nhận áp dụng.
- [ ] Đã xác định asset, dữ liệu, actor và trust boundary.
- [ ] Có owner thực thi và reviewer/approver đúng vai trò.
- [ ] Có điều kiện/trigger khi requirement áp dụng.
- [ ] Phát biểu rõ thành phần nào **phải làm gì**.
- [ ] Phát biểu điều gì **không được xảy ra** khi có rủi ro.
- [ ] Có failure behavior khi thiếu principal, policy, dependency hoặc context.
- [ ] Có scope rõ về endpoint/service/worker/environment.
- [ ] Không dùng từ mơ hồ nếu chưa định nghĩa.
- [ ] Không nhồi nhiều nghĩa vụ không liên quan vào một câu.
- [ ] Không chỉ nêu công cụ mà bỏ qua security property.
- [ ] Có dependency và điều kiện áp dụng/ngoại lệ nếu cần.
- [ ] Có positive acceptance criteria để bảo đảm nghiệp vụ hợp lệ.
- [ ] Có negative/boundary/bypass criteria theo threat model.
- [ ] Có cách test hoặc audit phù hợp với claim.
- [ ] Nếu có ngưỡng, đã nêu đơn vị, mốc đo, window, denominator và nguồn phê duyệt.
- [ ] Có phương án đo việc thực thi trên môi trường/phiên bản đúng.
- [ ] Đã review tính khả thi và xung đột với các yêu cầu khác.
- [ ] Có traceability tới control/design/implementation.
- [ ] Có test IDs và expected evidence references.
- [ ] Có xử lý trạng thái Not verified/Blocked/Insufficient evidence riêng.
- [ ] Có risk treatment/exception process nếu không đáp ứng.
- [ ] Có trigger review khi thay threat, API, data flow, identity hoặc chuẩn áp dụng.
- [ ] Có người chịu trách nhiệm cập nhật requirement và kiểm tra lại sau thay đổi.

Checklist giúp phát hiện thiếu sót nhưng **không thay thế review thiết kế, kiểm thử và đánh giá hiệu quả control trong thực tế**.

## 24. Bài tập thực hành

### Bài tập 1 — Chuyển câu mơ hồ thành requirement

Câu ban đầu:

> “Báo cáo đơn hàng phải bảo mật.”

Hãy xác định:

1. Loại dữ liệu nào trong báo cáo?
2. Ai được xuất?
3. Xuất qua đường nào, tới đích nào?
4. Ngữ cảnh tenant và scope được quyết định ở đâu?
5. Hành vi khi không có authorization hoặc destination approval?
6. Những positive/negative tests nào cần có?

**Đáp án tham khảo:**

> Với báo cáo chứa dữ liệu nhãn Confidential, report service phải kiểm tra quyền trên từng record và tenant theo principal được xác minh, đồng thời xác nhận đích nhận được policy cho phép trước khi phát hành artifact; nếu thiếu quyền hoặc chưa xác định được đích hợp lệ, hệ thống không được phát download link hoặc gửi nội dung ra ngoài.

### Bài tập 2 — Phát hiện requirement trộn nhiều nghĩa vụ

Câu ban đầu:

> “Ứng dụng phải dùng TLS, kiểm tra JWT, mã hóa database, ghi log mọi request và backup hằng ngày.”

Hãy tách thành ít nhất năm requirements, mỗi yêu cầu có scope, owner và test riêng. Xem liệu “backup hằng ngày” có thực sự phù hợp RPO/RTO và data classification hay chỉ là một giả định.

**Gợi ý:** phân biệt transport, authentication, data-at-rest, audit và recovery.

### Bài tập 3 — Viết negative test

Requirement:

> “Support agent được đọc order của tenant được giao, nhưng không được đọc order tenant khác.”

Viết test cho:

- Agent đọc đúng tenant.
- Agent đổi path ID sang tenant khác.
- Agent thay tenant header.
- Agent dùng bulk export.
- Agent bị thu hồi assignment nhưng cache chưa hết hạn.

**Tiêu chí:** không chỉ kiểm tra HTTP status; cần xem dữ liệu trả về, audit, cache và resource ownership.

### Bài tập 4 — Từ requirement tới evidence

Hãy lập RTM cho yêu cầu “Credential đã revoke không được dùng để mở session mới”, với:

- Source risk.
- Control owner.
- Token/credential type.
- Revocation semantics.
- Positive và negative tests.
- System of record.
- Evidence cần giữ.
- Mốc retest khi có thay đổi identity provider.

Không được viết “Verified” trước khi có test run và review.

## 25. Câu hỏi tự kiểm tra

1. Security requirement khác policy, control, implementation và test case như thế nào?
2. Vì sao “ứng dụng phải an toàn” không thể xem là requirement chất lượng?
3. Một yêu cầu có thể đo được nhưng vẫn không phù hợp rủi ro vì sao?
4. Những thành phần nào cần có để một requirement trở nên đơn nghĩa và testable?
5. Vì sao nên tách “phải xác thực” và “phải kiểm tra quyền trên object”?
6. Khi nào dùng requirement về outcome, khi nào cần thêm technology constraint?
7. Vì sao một JWT hợp lệ không đủ chứng minh user được phép xem mọi order?
8. Threat model giúp viết negative tests thế nào?
9. Một requirement không có nguồn risk/policy/obligation rõ có vấn đề gì?
10. Tại sao requirement cần ghi điều kiện khi không xác định được policy decision?
11. Trường hợp nào nên dùng default deny, và khi nào cần một degraded mode được phê duyệt?
12. Làm sao phân biệt việc phê duyệt requirement với verification control hiệu quả?
13. Vì sao một mock repository test chưa chứng minh RLS hoặc DB isolation?
14. Nếu xây API bulk export mới, requirement tenant isolation cũ cần đánh giá lại ra sao?
15. Gherkin scenarios có được tính là bằng chứng test đã PASS không? Vì sao?
16. Muốn đo thời gian xử lý alert, phải định nghĩa những yếu tố nào?
17. Một requirement cho session revoke cần ghi thêm semantics gì để có thể kiểm chứng?
18. Vì sao không tự áp một thời hạn retention hoặc nghĩa vụ consent cho mọi dữ liệu?
19. RTM giúp phát hiện những loại gap nào?
20. Nếu 15/20 requirements đã có evidence, có thể nói hệ thống an toàn 75% không?
21. Khi phát hiện requirement mâu thuẫn với privacy minimization, cần xử lý thế nào?
22. Vì sao risk acceptance không làm requirement tự động đạt?
23. Một requirement nên thay đổi version khi có những tác động nào?
24. Yêu cầu log mọi secret access cần lưu event gì và không được lưu gì?
25. Nêu ba security requirements cho một luồng đổi MFA, kèm mỗi requirement một negative test.
26. Hãy sửa câu “Phải có encryption tốt” thành phát biểu có scope, baseline và acceptance criteria.
27. Ai có trách nhiệm review applicability, thiết kế control, test và residual risk?
28. Những evidence nào cần trước khi kết luận SEC-ORD-001 đạt trên production?

## 26. Tổng kết

**Viết security requirement** là chuyển một rủi ro, threat scenario, security objective hoặc nghĩa vụ có áp dụng thành **phát biểu bắt buộc rõ ràng, có phạm vi, có trách nhiệm và có thể kiểm chứng**. Requirement tốt mô tả **chủ thể, điều kiện, tài nguyên, hành vi phải thực hiện/không được xảy ra, failure behavior và acceptance criteria**, đồng thời giữ liên kết tới source, control, test và evidence. Cần ưu tiên **atomic, unambiguous, feasible, risk-driven và testable**; tránh khẩu hiệu, công cụ thay cho mục tiêu, ngưỡng vô căn cứ và tình trạng thiếu owner. Với **SECURITY_SECURITY_ASSURANCE**, requirements là nền để tổ chức **design review, security testing, audit, remediation và retest**; mỗi kết luận phải chỉ rõ scope, phiên bản, môi trường và mức bằng chứng, phân biệt **Approved**, **Implemented** và **Verified**. Khi kiến trúc, threat, policy hoặc sản phẩm thay đổi, requirements và ma trận kiểm chứng cũng phải được cập nhật để duy trì assurance liên tục.

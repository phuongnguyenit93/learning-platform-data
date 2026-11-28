# Exception compliance: Quản lý ngoại lệ tuân thủ có kiểm soát và bằng chứng

Một tổ chức áp dụng chính sách rằng mọi tài khoản quản trị production phải dùng xác thực đa yếu tố (MFA). Tuy nhiên, một hệ thống legacy không hỗ trợ MFA trực tiếp; nhóm vận hành đề nghị cho phép truy cập bằng mật khẩu trong ba tháng để kịp hoàn thành nâng cấp. Nếu đơn giản đánh dấu yêu cầu “đã được miễn”, doanh nghiệp có thể đánh mất khả năng kiểm soát rủi ro, trách nhiệm phê duyệt và lịch sử không tuân thủ. Nếu từ chối mọi ngoại lệ bất kể hoàn cảnh, tổ chức có thể buộc đội kỹ thuật tự tạo cách lách chính sách không được giám sát.

**Exception compliance** là năng lực nhận diện, đánh giá, phê duyệt (khi được phép), giới hạn, giám sát và kết thúc những trường hợp **không đáp ứng một yêu cầu kiểm soát hoặc tiêu chí tuân thủ ở phạm vi cụ thể**, đồng thời duy trì bằng chứng về trạng thái thực tế và nghĩa vụ còn phải thực hiện. Ngoại lệ là một **quyết định quản trị có điều kiện**, không phải thao tác đổi kết quả kiểm tra từ FAIL thành PASS.

Trong chương **Compliance assurance** của module **SECURITY_SECURITY_ASSURANCE**, bài này tiếp cận ngoại lệ theo mô hình bảo đảm an ninh dựa trên bằng chứng: từ yêu cầu và rủi ro, tới security controls, kiểm tra hiện trạng, phân quyền quyết định, theo dõi hạn khắc phục và retest. Mục tiêu là giúp tổ chức đánh giá trung thực rằng **điều gì đã đạt, điều gì chưa đạt, ngoại lệ nào được cho phép, căn cứ là gì và rủi ro còn lại được kiểm soát đến đâu** trong quá trình phát triển và vận hành liên tục.

Sau bài học, người học có thể phân biệt các loại ngoại lệ; phân tích tính hợp lệ về chính sách, hợp đồng và pháp luật; thiết kế exception register và workflow; đánh giá compensating controls; tạo bằng chứng audit; theo dõi thời hạn, drift và khắc phục; xây dựng kết luận assurance có thể truy vết.

## 1. Hiểu đúng “ngoại lệ tuân thủ”

Không phải mọi trường hợp chưa đạt yêu cầu đều là ngoại lệ hợp lệ. Trước tiên phải phân biệt **sự kiện thực tế**, **yêu cầu áp dụng**, **cơ chế cho phép** và **quyết định xử lý rủi ro**.

| Khái niệm | Ý nghĩa thực tế | Có tự thay đổi kết quả control không? |
|---|---|---|
| **Noncompliance / nonconformity** | Một yêu cầu áp dụng không được đáp ứng tại đối tượng hoặc thời kỳ đánh giá. | Không; là tình trạng/nhận định dựa trên bằng chứng. |
| **Deviation** | Hành vi hoặc cấu hình lệch khỏi quy trình, chuẩn hay baseline đã định. | Không; cần xem đó là lệch được cho phép hay sai phạm. |
| **Policy exception / waiver** | Sự cho phép có phạm vi, điều kiện và thời hạn đối với một yêu cầu **nội bộ** trong thẩm quyền tổ chức. | Không mặc nhiên; có thể cho phép vận hành có điều kiện nhưng vẫn phải báo đúng mức đạt control. |
| **Risk acceptance** | Chủ thể có thẩm quyền quyết định chấp nhận rủi ro còn lại trong giới hạn xác định. | Không; quyết định rủi ro không chứng minh control hoạt động. |
| **Compensating control** | Biện pháp khác giảm một phần hoặc toàn bộ rủi ro do yêu cầu gốc chưa được đáp ứng. | Phải kiểm chứng hiệu lực và tính phù hợp; không mặc nhiên tương đương hoặc được bên áp yêu cầu công nhận. |
| **Temporary mitigation** | Hành động giảm phơi nhiễm trước khi sửa triệt để. | Không; phải ghi hạn chế và kiểm tra thực tế. |
| **Corrective action** | Biện pháp xử lý nguyên nhân không phù hợp, tránh tái diễn. | Chỉ chứng minh khắc phục khi có retest đúng phạm vi. |
| **Formal exemption under a rule** | Trường hợp được văn bản quy phạm, chuẩn, chương trình hoặc hợp đồng cho phép loại trừ theo điều kiện cụ thể. | Tùy văn bản; cần chứng cứ rằng điều kiện áp dụng thực sự được đáp ứng. |

**Ba câu hỏi then chốt:** (1) yêu cầu nào bị lệch, (2) ai có thẩm quyền cho phép điều gì, và (3) dữ liệu nào chứng minh kiểm soát/rủi ro đang ở trạng thái thực tế nào?

Ví dụ: đội ứng dụng có thể phê duyệt ngoại lệ với quy định nội bộ “mọi gói thư viện phải được cập nhật trong 30 ngày” nếu chính sách phân quyền như vậy. Nhưng không thể chỉ bằng chữ ký nội bộ để “miễn” một nghĩa vụ pháp lý bắt buộc, một điều khoản hợp đồng không cho phép ngoại lệ hoặc yêu cầu của cơ quan giám sát. Khi vấn đề liên quan pháp luật, hợp đồng hay quy định ngành, phải tham vấn người phụ trách pháp lý/compliance và xem chính xác điều kiện áp dụng.

### 1.1. Tính hợp lệ khác hiệu lực bảo mật

Giả sử một ngoại lệ đã được người có thẩm quyền phê duyệt đúng quy trình nhưng biện pháp bù trừ vẫn chưa được triển khai. Khi đó:

- **Quy trình phê duyệt:** có thể đạt yêu cầu về thủ tục.
- **Kiểm soát gốc:** vẫn chưa đạt tại đối tượng được ngoại lệ.
- **Biện pháp bù trừ:** chưa đạt cho tới khi có bằng chứng hoạt động.
- **Mức rủi ro còn lại:** có thể cao hơn mức đã phê duyệt, buộc đánh giá hoặc thu hồi quyết định.
- **Kết luận tổng thể:** không được dùng câu “đã phê duyệt” để suy ra “an toàn/tuân thủ đầy đủ”.

Phân tách các trục này giúp auditor nhìn thấy thực trạng thay vì một nhãn “Compliant with exceptions” thiếu giải thích.

## 2. Xác định yêu cầu gốc và quyền cho phép ngoại lệ

Trước khi xét đề nghị ngoại lệ, phải lập **requirement applicability mapping**: yêu cầu đến từ đâu, áp dụng cho ai, khi nào, trên dữ liệu và hệ thống nào, có lựa chọn thay thế hay điều kiện loại trừ chính thức không.

| Nguồn yêu cầu | Ví dụ | Vấn đề cần làm rõ |
|---|---|---|
| **Pháp luật/quy định** | Nghĩa vụ bảo vệ dữ liệu, lưu hồ sơ, an toàn theo ngành. | Phạm vi tài phán, đối tượng áp dụng, điều kiện, cơ chế miễn trừ hợp pháp nếu có và cơ quan có thẩm quyền. |
| **Hợp đồng/DPA/SLA** | Cam kết thông báo sự cố, giới hạn subprocessor, thời gian xử lý dữ liệu hoặc yêu cầu mã hóa. | Bên nào có thể thay đổi/waive, thủ tục sửa hợp đồng, thời điểm hiệu lực và quyền của khách hàng. |
| **Chuẩn hoặc chương trình chứng nhận** | Một bộ yêu cầu kiểm soát được tổ chức tuyên bố áp dụng hoặc chương trình đánh giá yêu cầu. | Chuẩn có cho phép biện pháp tương đương/ngoại lệ không; cách báo cáo phạm vi và nonconformity ra sao. |
| **Chính sách nội bộ** | MFA cho quản trị, quản lý bản vá, code review, giữ log. | Ai sở hữu chính sách, cơ chế xin exception, mức rủi ro được quyền phê duyệt. |
| **Baseline hoặc security standard kỹ thuật** | Cấu hình hệ điều hành, network segmentation, encryption settings. | Baseline được thừa kế từ chính sách nào, rủi ro và cách kiểm chứng bù trừ. |
| **Cam kết với khách hàng/cơ quan kiểm toán** | Các tuyên bố assurance và remediation đã cam kết. | Có bị ràng buộc kỳ hạn/thủ tục thông báo hay cần sự chấp thuận bên ngoài không. |

### 2.1. Phân biệt yêu cầu “bắt buộc” và hướng dẫn

Một framework thường gồm nguyên tắc, yêu cầu, hướng dẫn và các cách triển khai tham khảo. Không nên gắn mọi khuyến nghị kỹ thuật thành nghĩa vụ pháp lý; cũng không được xem yêu cầu hợp đồng bắt buộc như tùy chọn. Người đánh giá cần lưu bản yêu cầu có **tên, phiên bản, điều khoản/định danh, ngày hiệu lực và phạm vi**.

Ví dụ tổ chức áp dụng một chuẩn nội bộ yêu cầu dùng thuật toán mã hóa cụ thể. Có thể có phương án kỹ thuật tương đương được hội đồng kiến trúc phê duyệt. Nhưng nếu một điều khoản hợp đồng yêu cầu thuật toán cụ thể và không có quyền sửa đổi đơn phương, phê duyệt kiến trúc nội bộ **không đủ** thay đổi cam kết với khách hàng.

### 2.2. Hệ quả của “không có thẩm quyền”

Nếu chưa xác định được cơ chế hợp lệ để cho phép lệch khỏi yêu cầu, có thể:

1. Tạm dừng hoặc giới hạn hoạt động không đáp ứng.
2. Sửa thiết kế để đáp ứng yêu cầu.
3. Đàm phán sửa đổi/đồng ý của bên có quyền theo hợp đồng, nếu được phép.
4. Xin quyết định/miễn trừ theo thủ tục luật định khi thật sự có cơ chế đó.
5. Báo cáo không phù hợp, xử lý rủi ro và theo dõi remediation.

**Risk acceptance chỉ quyết định doanh nghiệp có tiếp tục chịu rủi ro trong thẩm quyền của mình**, không biến nghĩa vụ pháp luật hoặc quyền của bên khác thành không còn hiệu lực.

## 3. Các tình huống tạo ngoại lệ trong hệ thống thực tế

Một ngoại lệ có thể xuất hiện trong cả development và operations:

| Tình huống | Yêu cầu bị lệch | Hướng đánh giá |
|---|---|---|
| Server legacy không hỗ trợ MFA trực tiếp. | Chính sách tài khoản quản trị phải dùng MFA. | Xét bastion, JIT, phân đoạn mạng, logging và kế hoạch thay platform. |
| Thiết bị OT không thể vá ngay vì dây chuyền sản xuất. | Patch SLA của tài sản rủi ro cao. | Xác định CVE/exposure, môi trường kiểm thử, virtual patching/segmentation, lịch bảo trì. |
| Database cũ chưa hỗ trợ mã hóa như baseline. | Encryption at rest theo chính sách/hợp đồng. | Kiểm tra nghĩa vụ áp dụng, quyền truy cập, encryption ở lớp khác, đánh giá rủi ro và hạn chuyển đổi. |
| SaaS không xuất đủ loại audit log. | Retention/monitoring control nội bộ. | Hạn quan sát, quyền nhà cung cấp, chứng cứ bù trừ, SLA thay đổi, cân nhắc vendor. |
| Tính năng mới chưa hoàn tất penetration testing. | Release security gate. | Rủi ro chức năng, dữ liệu, exposure, test tối thiểu, điều kiện giới hạn rollout. |
| Lỗ hổng thư viện chưa có bản vá upstream. | Vulnerability remediation deadline. | Chặn đường khai thác, theo dõi advisory, đánh giá code path, lịch kiểm tra lại. |
| Nhà cung cấp chưa có chứng cứ theo phạm vi hợp đồng. | Third-party assurance evidence. | Ghi evidence gap, yêu cầu bổ sung, tránh coi thiếu bằng chứng là đã đạt. |
| Nhà quản trị cần truy cập khẩn cấp ngoài change window. | Quy trình phê duyệt trước và quyền tạm thời. | Break-glass có logging, hai người xác nhận hậu kiểm, thu hồi, thời gian hiệu lực. |

Một vấn đề có thể được xử lý bằng nhiều **loại hồ sơ khác nhau**: ngoại lệ chính sách, incident, finding, remediation ticket, contractual deviation hoặc waiver chính thức. Chúng cần **liên kết ID**, không gộp thành một biểu mẫu mơ hồ.

## 4. Định nghĩa phạm vi ngoại lệ chính xác

Một phê duyệt như “miễn áp dụng MFA cho hệ thống legacy” quá rộng để kiểm soát. Ngoại lệ nên mô tả được **tập đối tượng và hành động** chịu hiệu lực, đủ để máy hoặc người đánh giá kiểm tra.

### 4.1. Trường cần có trong exception register

| Nhóm trường | Nội dung |
|---|---|
| **Định danh** | Exception ID ổn định, trạng thái, version, liên kết finding/incident/change. |
| **Yêu cầu** | Requirement/control ID, văn bản và phiên bản, tiêu chí chưa đạt, nguồn nghĩa vụ. |
| **Đối tượng** | Asset/resource IDs, account, cluster, environment, owner, data class, region, dịch vụ. |
| **Lệch cụ thể** | Điều gì đang không đáp ứng, thời điểm phát hiện, bằng chứng kỹ thuật, mức độ và nguyên nhân. |
| **Rủi ro** | Threat scenario, tác động tới bảo mật/nghiệp vụ/pháp lý, xác suất, exposure, risk rating. |
| **Biện pháp hiện có và bù trừ** | Control ID, triển khai, bằng chứng hoạt động, limitation và người chịu trách nhiệm. |
| **Phê duyệt** | Business/data/control owner, security/risk/compliance/legal theo quyền; thời điểm, phạm vi và điều kiện. |
| **Thời hạn** | Ngày bắt đầu, hạn hết hiệu lực, mốc kiểm tra giữa kỳ, remediation deadline. |
| **Giám sát** | Telemetry, ngưỡng cảnh báo, sự kiện phải đánh giá lại, người nhận/escalation. |
| **Kết thúc** | Bằng chứng khắc phục, retest, kết quả, người đóng và các nhiệm vụ còn tồn đọng. |

### 4.2. Ngoại lệ cần “hẹp nhất có thể”

- Theo **đối tượng**: một nhóm server có asset ID, không phải “toàn hệ thống production”.
- Theo **quyền**: một vai trò cần sử dụng, không phải mọi tài khoản administrator.
- Theo **hành động**: một đường vào quản trị legacy, không phải mọi hình thức truy cập.
- Theo **thời gian**: có hiệu lực và hết hạn; không dùng “cho đến khi nâng cấp xong” nếu không có deadline.
- Theo **dữ liệu**: chỉ loại dữ liệu đã được đánh giá.
- Theo **địa điểm/vùng**: giới hạn trong môi trường, khu vực hoặc network đã xác nhận.

Nếu tài sản được đổi, nhóm người dùng mở rộng, dữ liệu nhạy cảm hơn hoặc dịch vụ được mở Internet, phạm vi phê duyệt **cần được xem lại**. Ngoại lệ không tự động “kế thừa” sang mọi tài sản mới cùng tên.

## 5. Vòng đời Exception compliance

~~~mermaid
flowchart TD
    A["Phát hiện lệch / đề nghị ngoại lệ"] --> B["Xác minh yêu cầu, scope và tính hợp lệ"]
    B --> C{"Có quyền phê duyệt ngoại lệ loại này?"}
    C -->|Không| D["Noncompliance: khắc phục / xử lý pháp lý-hợp đồng"]
    C -->|Có| E["Đánh giá rủi ro và phương án"]
    E --> F["Xác định control bù trừ + phép kiểm tra"]
    F --> G{"Đủ bằng chứng và rủi ro trong thẩm quyền?"}
    G -->|Không| H["Từ chối, giảm phạm vi hoặc yêu cầu khắc phục"]
    G -->|Có| I["Phê duyệt có điều kiện, expiry, owner"]
    I --> J["Thực thi, kiểm thử và giám sát liên tục"]
    J --> K{"Có thay đổi, hết hạn hoặc vi phạm điều kiện?"}
    K -->|Có| L["Tái đánh giá, thu hồi hoặc gia hạn có kiểm soát"]
    L --> E
    K -->|Không| M["Khắc phục nguyên nhân gốc theo kế hoạch"]
    M --> N["Retest control gốc, xác minh scope"]
    N --> O{"Đạt yêu cầu?"}
    O -->|Không| E
    O -->|Có| P["Đóng ngoại lệ, lưu lịch sử bằng chứng"]
~~~

### Bước 1 — Tạo request gắn với evidence

Người đề nghị mô tả requirement, asset, nguyên nhân chưa đáp ứng, thời gian cần, dữ liệu/phơi nhiễm và lý do chưa thể sửa ngay. Đi kèm bằng chứng như inventory, kết quả scanner, policy export, kiểm thử quyền hoặc tài liệu giới hạn sản phẩm. Không chấp nhận yêu cầu chỉ ghi “không phù hợp công nghệ hiện tại” mà thiếu chứng minh.

### Bước 2 — Kiểm tra applicability và thẩm quyền

Compliance/Legal hoặc control owner xác định yêu cầu có áp dụng thực sự, cần phân loại là policy exception hay noncompliance pháp lý/hợp đồng, có quyền phê duyệt/điều chỉnh hay không. Nếu chưa rõ luật hoặc điều khoản, đánh dấu **PENDING LEGAL/CONTRACT REVIEW**, không cho phép mặc định.

### Bước 3 — Phân tích nguyên nhân và lựa chọn

Tìm root cause: không tương thích phần mềm, sai kiến trúc, thiếu ngân sách, phụ thuộc nhà cung cấp, quy trình chưa trưởng thành hay ưu tiên release. Xem các phương án: sửa ngay, thay thiết kế, tắt chức năng, giảm dữ liệu, triển khai control bù trừ, thay vendor hoặc chấp nhận rủi ro có điều kiện.

### Bước 4 — Đánh giá rủi ro và compensating controls

Kết hợp độ quan trọng dữ liệu, mức truy cập, exploitability, exposure, thời gian kéo dài, khả năng phát hiện, tác động và tác dụng của control bù trừ. Phải có **bằng chứng control bù trừ đã được thiết kế và thực thi**, không chỉ kế hoạch lắp đặt.

### Bước 5 — Phê duyệt có điều kiện

Người có thẩm quyền ký hoặc xác nhận trong hệ thống quản trị: đúng control, scope, hạn, điều kiện không được vượt, owner, việc giám sát, lịch sửa và hậu quả khi vi phạm. Tránh tự phê duyệt bởi cùng cá nhân tạo cấu hình yếu và chấp nhận rủi ro, nhất là với ngoại lệ nghiêm trọng.

### Bước 6 — Thực thi, kiểm tra và theo dõi

Xác minh chính những biện pháp được đặt làm điều kiện phê duyệt: bastion thực hiện MFA, đường trực tiếp bị chặn, log tới SIEM, access review theo lịch hoặc node được phân đoạn. Đánh giá lại khi có incident, CVE mới, thay đổi kiến trúc hoặc bằng chứng suy giảm.

### Bước 7 — Expiry, quyết định tiếp tục hoặc thu hồi

Khi đến hạn, không mặc định phê duyệt tiếp. Cần lấy bằng chứng mới, lý do chậm khắc phục, rủi ro cập nhật, lựa chọn thay thế, người duyệt và hạn mới nếu được phép. Nếu thiếu quyết định mới, exception chuyển trạng thái **EXPIRED / NOT AUTHORIZED**, escalated theo chính sách; hành động cô lập hoặc dừng dịch vụ cần do người có thẩm quyền thực hiện theo kế hoạch an toàn.

### Bước 8 — Retest và đóng

Sau khi vá, nâng cấp, sửa IAM hoặc đổi thiết kế, chạy lại phép kiểm tra **control gốc** trên mọi đối tượng thuộc scope; xác nhận không còn đường bypass, biện pháp tạm/đặc quyền tạm được thu hồi, finding được đóng theo bằng chứng. Lưu lịch sử ngoại lệ và những thời kỳ chưa đáp ứng, không xóa dấu vết để báo cáo kỳ trước thành PASS.

## 6. Đánh giá rủi ro thay vì chấm điểm theo cảm giác

Rủi ro còn lại cần được đánh giá theo kịch bản đe dọa và điều kiện thực tế, không chỉ ghép một CVSS với một mức “medium”.

### 6.1. Phân tích theo tình huống

Hãy hỏi:

1. **Tài sản và dữ liệu:** ảnh hưởng tới dịch vụ, dữ liệu nhạy cảm hoặc tính an toàn vật lý thế nào?
2. **Threat actor và capability:** ai có thể khai thác sự thiếu control, cần điều kiện gì?
3. **Attack path/exposure:** đường từ Internet, mạng nội bộ, quản trị từ xa, đối tác, CI/CD hay tài khoản bị lộ?
4. **Tác động:** mất bí mật, sai toàn vẹn, gián đoạn, nghĩa vụ pháp lý/hợp đồng hay gian lận?
5. **Khả năng phát hiện và phản ứng:** có telemetry, triage, on-call và containment trong thời gian phù hợp không?
6. **Compensating controls:** làm thay đổi khả năng/độ nghiêm trọng đến đâu, bằng chứng hiệu lực là gì?
7. **Thời hạn:** ngoại lệ kéo dài qua bao lâu, có tăng exposure hoặc vượt ngưỡng rủi ro theo thời gian không?
8. **Bối cảnh thay đổi:** patch mới, sự cố bên ngoài, mức tải, vùng hoạt động hoặc quyền mới có làm kết luận cũ lỗi thời?

### 6.2. Ma trận quyết định minh họa

| Mức rủi ro sau kiểm soát bù trừ | Ví dụ điều kiện | Hướng xử lý gợi ý |
|---|---|---|
| **Không thể chấp nhận** | Dữ liệu đặc biệt nhạy cảm phơi lộ rộng, điều kiện bắt buộc không thể bỏ qua hoặc đường tấn công còn hoạt động. | Không phê duyệt ngoại lệ trong thẩm quyền hiện tại; hạn chế/dừng, khắc phục hoặc xử lý pháp lý/hợp đồng. |
| **Cao** | Bỏ control phòng ngừa quan trọng, exposure lớn, phát hiện yếu hoặc thời hạn dài. | Escalate risk owner cấp cao, giảm phạm vi, đặt gate và kiểm tra thường xuyên nếu có thể được cho phép. |
| **Trung bình** | Exposure đã được giới hạn, có biện pháp bù trừ hữu hiệu, owner và remediation rõ. | Có thể xét ngoại lệ ngắn hạn theo thẩm quyền và kỳ kiểm tra xác định. |
| **Thấp** | Lệch nhỏ trong scope hẹp, không ảnh hưởng mục tiêu trọng yếu và có bằng chứng kiểm soát tương đương. | Quy trình phê duyệt đơn giản hơn nhưng vẫn lưu lý do, điều kiện và hạn. |

Đây là **khung đánh giá minh họa**, không phải phương pháp tính rủi ro chuẩn. Tổ chức phải dùng risk appetite, ma trận đánh giá và quyền phê duyệt được ban hành. Với nghĩa vụ pháp lý bắt buộc, mức “thấp” không tự cho phép một hành vi không đáp ứng.

### 6.3. Đừng nhầm “thời gian ngoại lệ” với thời gian an toàn

Ngoại lệ 90 ngày có thể phù hợp với dự án nâng cấp nếu rủi ro được kiểm soát. Nhưng nếu xuất hiện khai thác đang diễn ra hoặc lỗ hổng nghiêm trọng mới, **điều kiện an toàn thay đổi ngay**. Phải có trigger để thu hồi hoặc đánh giá lại trước ngày hết hạn, không chờ vòng review kế tiếp.

## 7. Compensating controls: Kiểm soát bù trừ có thực sự tương xứng?

Biện pháp bù trừ chỉ có ý nghĩa khi **giảm được rủi ro của mục tiêu control gốc**, có thể thực thi và đo được. Một biện pháp giám sát không phải lúc nào cũng thay thế phòng ngừa; một biện pháp phòng ngừa ở lớp khác không mặc nhiên được framework hoặc hợp đồng chấp nhận.

### 7.1. Đánh giá bằng mô hình mục tiêu–mối đe dọa–biện pháp

Giả sử control gốc là “MFA khi truy cập quản trị máy chủ”. Mục tiêu là giảm nguy cơ tài khoản bị chiếm và sử dụng trái phép. Hệ thống legacy không có MFA trong ứng dụng nhưng hỗ trợ quản trị qua bastion.

| Biện pháp đề xuất | Lợi ích | Bằng chứng cần xem | Giới hạn |
|---|---|---|---|
| MFA tại bastion/JIT gateway | Tăng đảm bảo xác thực trước khi vào môi trường quản trị. | Effective access policy, test đăng nhập, danh sách người dùng. | Nếu còn đường SSH/RDP trực tiếp, mục tiêu có thể chưa được đáp ứng. |
| Chặn quản trị trực tiếp ngoài bastion | Giảm bypass path. | Network/IAM config, thử kết nối từ đường không được phép. | Rule có thể drift hoặc server mới chưa nằm trong scope. |
| Least privilege và session expiry | Giảm thời gian/quyền khi tài khoản bị lộ. | Role mapping, thời hạn phiên, access review. | Không thay được việc kiểm soát chứng thực nếu token bị lạm dụng. |
| Session recording + alert | Phát hiện và hỗ trợ điều tra hành vi nguy hiểm. | Audit end-to-end, synthetic alert, người trực xác nhận. | Phát hiện không nhất thiết ngăn hành vi kịp thời. |
| Segmentation và allowlist | Giảm vùng nguồn được phép kết nối. | Policy, thực nghiệm reachability, asset inventory. | IP tin cậy vẫn có thể bị xâm phạm. |
| Kế hoạch nâng cấp/thay thế | Loại bỏ lý do ngoại lệ trong tương lai. | Change plan, budget, milestones, test sau nâng cấp. | Kế hoạch chưa triển khai không giảm rủi ro hiện tại. |

Để chứng minh mục tiêu được kiểm soát phù hợp, cần **kiểm thử đường vào bình thường, đường bypass, tài khoản đặc quyền, break-glass, service identities và giám sát**. Một ảnh màn hình “MFA enabled” tại bastion không đủ nếu còn network path trực tiếp vào server.

### 7.2. Kiểm chứng theo mức tương đương

Một câu hỏi hữu ích là: “Khi control gốc bị thiếu, kẻ tấn công có thể làm gì mà biện pháp bù trừ chưa ngăn hoặc chưa phát hiện đủ sớm?” Nếu phát hiện được lỗ hổng đó, mô tả limitation và mức rủi ro còn lại.

Đối với một chương trình tuân thủ bên ngoài, việc dùng compensating controls **chỉ được công nhận theo cơ chế của chương trình đó**. Không dùng đánh giá nội bộ “tương đương về kỹ thuật” làm bằng chứng rằng cơ quan kiểm toán/chương trình đã chấp nhận một thay thế chưa được cho phép.

## 8. Quản trị phê duyệt: Ai có quyền và ai phải độc lập?

Không nhất thiết mọi ngoại lệ đều cần hội đồng cấp cao. Nhưng thẩm quyền cần được xác định trước và tăng theo rủi ro, nguồn yêu cầu và tác động.

| Vai trò | Trách nhiệm thông thường |
|---|---|
| **Requestor / System Owner** | Mô tả lệch, cung cấp bằng chứng, đề xuất phạm vi và kế hoạch khắc phục. |
| **Control Owner** | Giải thích mục tiêu yêu cầu, xem kỹ thuật và phép kiểm tra của biện pháp thay thế. |
| **Security/Risk Assessor** | Đánh giá threat scenario, residual risk, coverage và điều kiện giám sát. |
| **Business/Data Risk Owner** | Quyết định chấp nhận rủi ro trong quyền được ủy quyền, với tác động nghiệp vụ/dữ liệu. |
| **Compliance/Legal/Privacy** | Kiểm tra yêu cầu áp dụng, điều kiện cho phép, nghĩa vụ báo cáo và các hạn chế pháp lý/hợp đồng. |
| **Operations / Engineering** | Triển khai, giám sát control bù trừ và remediation đúng hạn. |
| **Internal Audit / Independent Reviewer** | Đánh giá tính phù hợp của quy trình, bằng chứng và kết luận; không tự thay vai trò chủ sở hữu quyết định. |
| **Governance Committee (khi áp dụng)** | Xem các ngoại lệ vượt ngưỡng, kéo dài hoặc có xung đột lợi ích đáng kể. |

### 8.1. Segregation of duties

Không nên để một người vừa đề nghị ngoại lệ, tự đánh giá rủi ro, tự phê duyệt, rồi tự xác nhận tất cả control bù trừ đều đạt mà không có review phù hợp. Với tổ chức nhỏ, có thể thiết lập kiểm tra chéo theo vai trò hoặc yêu cầu xem xét định kỳ bởi bộ phận độc lập trong phạm vi khả thi.

### 8.2. Ma trận thẩm quyền

Ví dụ nội bộ có thể quy định:

- Ngoại lệ thấp, ngắn hạn: control owner và service owner phê duyệt theo chính sách.
- Ngoại lệ trung bình: security/risk review và business owner phê duyệt.
- Ngoại lệ cao: cấp có thẩm quyền cao hơn, điều kiện bù trừ và lịch review chặt.
- Liên quan pháp luật/hợp đồng hoặc yêu cầu bên ngoài: **kiểm tra tính hợp lệ riêng**, tham vấn/được chấp thuận bởi chủ thể có quyền phù hợp; không chỉ tăng cấp risk approver.

Không tự đưa ra một bảng thẩm quyền chung cho mọi tổ chức; các ngưỡng và chức danh minh họa phải được nội bộ phê duyệt.

## 9. Quản lý ngoại lệ khẩn cấp và break-glass

Một số tình huống đòi hành động nhanh hơn chu kỳ phê duyệt thông thường: sự cố production nghiêm trọng, cần truy cập hệ thống khôi phục hoặc thay đổi firewall để ngăn sự cố lan rộng. Điều đó không có nghĩa cho phép ngoại lệ không có giới hạn.

### 9.1. Điều kiện cho emergency exception

1. Định nghĩa trước **trigger** như incident severity, tác động dịch vụ và quyền khẩn.
2. Giới hạn phạm vi, thời gian và tài khoản được sử dụng; cấp quyền tạm với expiry nếu hệ thống hỗ trợ.
3. Bảo đảm có xác thực, log, session recording, two-person review hoặc biện pháp thích hợp với rủi ro.
4. Thông báo người trực và người phê duyệt, ghi decision log cùng lý do không thể chờ workflow thường.
5. Sau sự cố, thực hiện **retrospective review** trong thời hạn theo chính sách và thu hồi quyền.
6. Nếu phát hiện misuse hoặc thiếu evidence, mở finding/incident và cải tiến playbook.

### 9.2. Không dùng khẩn cấp để làm lỗ hổng thường trực

Nếu một hệ thống phải sử dụng break-glass hằng tuần vì cấu hình kém, đó là dấu hiệu **root cause chưa được xử lý**. Nên theo dõi số lần, người sử dụng, lý do và khả năng thay thiết kế, thay vì gia hạn quyền khẩn vô thời hạn.

## 10. Evidence chain và trạng thái kiểm soát trong kỳ audit

Đây là điểm mấu chốt của compliance assurance: **một ngoại lệ được phê duyệt không xóa được sự thật lịch sử rằng yêu cầu gốc chưa được đáp ứng**.

~~~mermaid
flowchart LR
    R["Requirement + scope + kỳ kiểm tra"] --> T["Test control gốc"]
    T --> V{"Kết quả kỹ thuật"}
    V -->|PASS| P["Lưu evidence và reviewer"]
    V -->|FAIL| F["Finding / nonconformity"]
    V -->|INCONCLUSIVE| G["Evidence gap"]
    F --> E["Exception request + risk assessment"]
    E --> A["Approval / rejection + điều kiện"]
    A --> C["Compensating control tests"]
    C --> M["Giám sát, hạn, remediation"]
    M --> RT["Retest control gốc"]
    RT --> H["Kết quả mới có version; không ghi đè lịch sử"]
~~~

### 10.1. Hai loại kết luận phải ghi riêng

| Trục | Câu hỏi | Ví dụ kết quả |
|---|---|---|
| **Control operating effectiveness** | Yêu cầu gốc có được đáp ứng trên đối tượng và kỳ đánh giá không? | **FAIL**: tài khoản không dùng MFA tại ứng dụng legacy. |
| **Exception governance conformance** | Ngoại lệ có hợp lệ, còn hạn, đúng scope, được phê duyệt, có bù trừ/giám sát như yêu cầu không? | **PASS** về quản lý ngoại lệ nếu mọi điều kiện quản trị được kiểm chứng. |
| **Compensating control effectiveness** | Biện pháp thay thế có vận hành thực tế và giảm rủi ro mục tiêu không? | **PASS/FAIL** tùy test gateway, firewall, audit và alert. |
| **Risk decision** | Chủ thể có thẩm quyền cho tiếp tục vận hành trong giới hạn nào? | **ACCEPTED UNTIL DATE** hoặc **REJECTED**. |
| **External requirement compliance** | Nghĩa vụ pháp luật/hợp đồng/chương trình có được đáp ứng hoặc cho phép cách xử lý đã chọn không? | Phải đánh giá riêng; có thể FAIL dù policy exception được duyệt. |

Một dashboard chỉ có hai trạng thái “compliant/noncompliant” dễ che khác biệt này. Nên bổ sung các trường **control_result, exception_status, risk_decision, compensating_control_result, external_obligation_status**.

### 10.2. Đánh giá trong cả kỳ

Giả sử ngoại lệ có hiệu lực từ ngày 10 đến ngày 30, nhưng yêu cầu áp dụng từ ngày 1. Không được suy ra cả tháng đã có phê duyệt. Nếu có gap ngày 1–9, phải ghi noncompliance tại kỳ đó và đánh giá biện pháp xử lý, tùy quy định đã phê duyệt.

Tương tự, một ngoại lệ hết hạn ngày 20, được ký gia hạn ngày 25 **không tự hợp thức hóa** giai đoạn ngày 21–24, trừ khi có cơ chế pháp lý/chính sách cho phép và bằng chứng cụ thể. Tập hợp period-of-time cần có lịch sử trạng thái, ngày hiệu lực, không chỉ trạng thái hiện tại.

## 11. Mẫu Exception register có thể truy vết

Mẫu YAML sau dùng cho mục đích học thuật, không phải cấu hình chuẩn của một hệ thống GRC:

~~~yaml
exception:
  id: "EXC-COMP-EXAMPLE-008"
  version: "1.0"
  title: "Legacy admin console lacks native MFA"
  request_status: "APPROVED_WITH_CONDITIONS"
  discovered_at_utc: "2026-11-10T08:00:00Z"
  effective_from_utc: "2026-11-15T00:00:00Z"
  expires_at_utc: "2027-02-15T00:00:00Z"

requirement:
  type: "internal-security-policy"
  id: "IAM-MFA-ADM-01"
  version: "2026.3"
  objective: "Giảm nguy cơ truy cập quản trị bằng thông tin xác thực bị lộ"
  original_control_result: "FAIL"
  legal_contract_review_required: true
  legal_contract_review_outcome: "NO_CONFLICT_IDENTIFIED_IN_REVIEW_SCOPE"

scope:
  environment: "production"
  application: "legacy-admin-console"
  assets: ["admin-vm-01", "admin-vm-02"]
  identities: ["authorized-human-admins-only"]
  allowed_entry_point: "approved-bastion"
  excluded: ["direct-admin-access", "third-party-vendor-access"]

risk_assessment:
  scenario: "Compromised administrator password"
  inherent_risk: "HIGH"
  residual_risk: "MEDIUM"
  assessment_date_utc: "2026-11-13T02:00:00Z"
  limitations:
    - "Native MFA not supported by application"
    - "Bastion compromise remains an attack scenario"

compensating_controls:
  - id: "MFA-AT-BASTION"
    implemented: true
    test_result: "PASS"
    evidence: "restricted/exceptions/008/mfa-bastion-test"
  - id: "DIRECT-ACCESS-BLOCK"
    implemented: true
    test_result: "PASS"
    evidence: "restricted/exceptions/008/network-deny-test"
  - id: "SESSION-AUDIT-ALERT"
    implemented: true
    test_result: "PASS"
    evidence: "restricted/exceptions/008/synthetic-alert-test"

approval:
  control_owner: "Identity Security Owner"
  risk_owner: "Business Service Owner"
  security_reviewer: "Security Assurance Team"
  decision_reference: "RISK-DECISION-EXAMPLE-008"
  decision_at_utc: "2026-11-14T05:00:00Z"
  conditions:
    - "No direct management path"
    - "Daily high-risk privileged activity review"
    - "Review immediately if the exposure changes"

monitoring:
  review_frequency: "weekly"
  next_review_date: "2026-12-05"
  triggers:
    - "new_admin_asset_or_credential"
    - "bastion_control_failure"
    - "security_incident"
    - "change_in_data_classification"

remediation:
  action: "Replace legacy admin module with MFA-capable version"
  accountable: "Application Platform Owner"
  planned_completion_date: "2027-01-31"
  verification: "Effective MFA test + no bypass path"
  finding_id: "FINDING-IAM-EXAMPLE-008"

assurance:
  original_control: "FAIL"
  exception_governance: "PASS"
  compensating_controls: "PASS_ON_TESTED_SCOPE"
  external_requirement: "NOT_DETERMINED_OUTSIDE_REVIEW_SCOPE"
  status_at_assessment: "ACTIVE_WITH_CONDITIONS"
~~~

Những ID, ngày, thời hạn và mức rủi ro ở đây là **ví dụ giả định**, không mang ý nghĩa chuẩn hay thời hạn áp dụng phổ quát. `original_control: FAIL` cùng `exception_governance: PASS` **không mâu thuẫn**: yêu cầu MFA tại ứng dụng chưa được đáp ứng nhưng quyết định ngoại lệ và biện pháp bù trừ đã được quản trị đúng phạm vi giả định.

### 11.1. Tránh thiếu bằng chứng về phê duyệt

Một dòng “approved by security” không đủ nếu không biết người phê duyệt, quyền được ủy quyền, nội dung đã xem, phiên bản đánh giá và thời điểm có hiệu lực. Cần lưu artifact phê duyệt điện tử hoặc biên bản phù hợp, có version và access control.

### 11.2. Tránh tham chiếu mơ hồ

Mỗi bằng chứng nên có ID ổn định, phạm vi, thời gian, nguồn và phép kiểm tra. Tránh liên kết đến “latest-report.pdf” có thể bị ghi đè. Nếu evidence chứa dữ liệu nhạy cảm, dùng link trong kho hạn quyền thay vì đưa toàn bộ log/token vào ticket.

## 12. Kiểm tra vận hành và giám sát ngoại lệ liên tục

Trong giai đoạn còn hiệu lực, một ngoại lệ nên được coi là **đối tượng giám sát** thay vì tài liệu chờ đến ngày hết hạn.

| Tín hiệu | Việc cần theo dõi | Phản ứng khi sai |
|---|---|---|
| **Control bù trừ** | Agent, bastion MFA, firewall, WAF, access review, audit event hoặc scanner hoạt động. | Cảnh báo owner; hạn chế/tạm dừng hoạt động nếu điều kiện an toàn không còn. |
| **Inventory drift** | Asset mới, account mới, namespace/region mới đi vào cùng đường truy cập. | Kiểm tra lại scope; chưa tự động cho phép đối tượng mới. |
| **Exposure thay đổi** | Endpoint chuyển từ private ra Internet; quyền tăng; dữ liệu nhạy cảm hơn. | Đánh giá lại risk rating và phê duyệt. |
| **Threat intelligence** | Khai thác đang diễn ra, advisory mới, lỗ hổng mới tác động đến asset. | Xem xét thu hồi ngoại lệ/triển khai mitigation ngay theo mức rủi ro. |
| **Remediation progress** | Mốc thiết kế, ngân sách, release, test và deployment. | Escalate khi trễ, không kéo hạn tự động. |
| **Thời hạn** | Trước ngày hết hạn có yêu cầu retest và quyết định mới. | EXPIRED/ESCALATED nếu không có quyết định đúng thẩm quyền. |
| **Vendor dependencies** | Nhà cung cấp thay sản phẩm, DPA, logging API hoặc điều kiện support. | Review nghĩa vụ, scope, control bù trừ và phương án thay. |
| **Incident or detection** | Alert cho thấy đường rủi ro còn bị khai thác. | Kích hoạt IR, containment, thu thập evidence, reassessment. |

### 12.1. Expiry automation

Có thể xây dựng workflow cảnh báo theo chu kỳ, ví dụ trước hạn 30/14/7 ngày tùy chính sách nội bộ; khi hết hạn, gắn cờ, khóa việc tự gia hạn và gửi escalation. Thông báo chỉ nhắc hạn **không thay thế** người đánh giá lại control và rủi ro.

### 12.2. Detect drift, không chỉ chứng minh baseline một lần

Nếu ngoại lệ cho phép đúng hai VM, nhưng deployment mở rộng thành tám VM, collector phải phát hiện asset drift. Nếu bastion đã bật MFA nhưng mạng mới tạo đường quản trị trực tiếp, kiểm tra bypass cần được chạy lại. Giám sát nên dựa vào inventory và cấu hình hiệu lực, không chỉ lời xác nhận hằng quý.

## 13. Audit evidence và tiêu chí chấp nhận hồ sơ ngoại lệ

Một auditor muốn xem được **toàn bộ đường đi quyết định**, không chỉ một trạng thái trong GRC.

### 13.1. Chuỗi bằng chứng tối thiểu

~~~mermaid
flowchart TD
    R["Requirement version + scope"] --> D["Kết quả test: noncompliance"]
    D --> F["Finding + nguyên nhân"]
    F --> Q["Exception request"]
    Q --> K["Risk assessment + legal/contract applicability"]
    K --> C["Compensating control design"]
    C --> T["Test output + raw evidence"]
    T --> A["Phê duyệt đúng thẩm quyền"]
    A --> M["Monitoring + review + expiry"]
    M --> P["Remediation/change artifact"]
    P --> V["Retest control gốc"]
    V --> Z["Closure và giữ lịch sử"]
~~~

### 13.2. Tiêu chí chất lượng evidence

- **Relevance:** dữ liệu chứng minh đúng control, điều kiện, rủi ro và phạm vi.
- **Authenticity/provenance:** xác định người/hệ thống thu thập, nguồn, phiên bản, timestamp.
- **Completeness:** bao phủ tất cả asset, identities và thời kỳ; không loại trừ âm thầm tài sản mới.
- **Integrity:** bản gốc và bản chuyển đổi có lịch sử/hashing/version khi phù hợp.
- **Timeliness:** bằng chứng không quá cũ so với sự thay đổi rủi ro.
- **Reproducibility:** có thể kiểm thử lại với truy vấn, script, tham số, input IDs.
- **Independence:** review và phê duyệt có mức tách biệt tương xứng.
- **Confidentiality/retention:** lưu đủ cho audit và điều tra nhưng không mở rộng quyền truy cập dữ liệu nhạy cảm.

Đặc biệt, **một hash không chứng minh nguồn đầy đủ**, ảnh cấu hình không chứng minh hiệu lực xuyên kỳ, và chứng nhận của nhà cung cấp không chứng minh mọi control của tenant đã đạt.

### 13.3. Không ghi đè lịch sử

Nếu control FAIL tháng 11, exception được duyệt tháng 12, control được sửa vào tháng 1, phải giữ cả ba sự kiện và kết luận theo thời kỳ. Bằng chứng mới có thể chứng minh **từ thời điểm retest** control đã đạt; nó không làm kỳ trước tự trở thành tuân thủ.

## 14. Kết luận PASS, FAIL và INCONCLUSIVE đúng bản chất

Nên tách các kết quả:

| Loại đánh giá | PASS | FAIL | INCONCLUSIVE |
|---|---|---|---|
| **Original control** | Đáp ứng yêu cầu gốc trên scope/kỳ. | Chứng cứ cho thấy không đáp ứng. | Không đủ chứng cứ xác định trạng thái. |
| **Exception authorization** | Đúng nguồn yêu cầu, cơ chế cho phép, phạm vi, người duyệt, hạn và điều kiện. | Thiếu quyền phê duyệt, hết hạn, vượt scope hoặc vi phạm điều kiện. | Không xác minh được quyền/phạm vi/hiệu lực. |
| **Compensating control** | Biện pháp được triển khai và hoạt động theo phép thử phù hợp. | Đường bypass hoặc control không hoạt động. | Chưa thử đủ phạm vi hoặc mất telemetry. |
| **Remediation** | Root cause được xử lý và retest đạt. | Khắc phục chưa xong hoặc retest thất bại. | Chưa có đủ bằng chứng nghiệm thu. |
| **External compliance** | Đáp ứng đúng điều kiện luật/hợp đồng/chương trình áp dụng. | Có bằng chứng không đáp ứng nghĩa vụ. | Applicability hoặc điều kiện chưa xác minh được. |

**NOT_APPLICABLE** chỉ dùng khi một yêu cầu thật sự không thuộc phạm vi có căn cứ, không dùng thay cho “có ngoại lệ” hoặc “chưa thử”. Một policy exception không biến requirement thành N/A nếu requirement vẫn áp dụng nhưng chưa được đáp ứng.

### 14.1. Ví dụ về hai báo cáo khác nhau

- Báo cáo kỹ thuật: “Control IAM-MFA-ADM-01 FAIL trên hai VM production, các đường truy cập khác đã kiểm tra đạt.”
- Báo cáo quản trị: “Exception EXC-008 ACTIVE đến ngày X, risk owner đã duyệt, bastion MFA và chặn direct path đạt các phép thử, remediation target ngày Y, external contractual compliance cần đánh giá riêng.”

Cả hai đều hữu ích và có thể đồng thời đúng. Điều không đúng là thay cả hai thành “compliant: true” mà không giải thích.

## 15. Ngoại lệ trong cloud, nhà cung cấp và chuỗi sản phẩm

### 15.1. Shared responsibility

Ở cloud, provider và khách hàng chịu trách nhiệm cho các lớp khác nhau. Nếu dịch vụ managed không xuất được loại log khách hàng cần, không thể tự viết “cloud provider đã chịu trách nhiệm” rồi đóng finding. Phải làm rõ: yêu cầu thuộc ai, nhà cung cấp cam kết gì, khách hàng có quyền cấu hình hoặc export nào, biện pháp thay thế và giới hạn điều tra.

### 15.2. Third-party exceptions

Nếu nhà cung cấp không cung cấp bằng chứng audit kịp kỳ đánh giá, đây có thể là **evidence exception** chứ chưa chứng minh control vendor vận hành sai. Tuy nhiên thiếu bằng chứng vẫn ngăn kết luận assurance mạnh. Cần xác định hợp đồng, người sở hữu quan hệ, deadline bổ sung và risk treatment. Không coi “vendor đã trả lời email” là evidence đủ cho control cụ thể.

### 15.3. Secure SDLC và release gates

Một đội phát triển có thể đề nghị release khi chưa hoàn tất penetration testing hoặc còn phát hiện medium. Để kiểm soát, cần scope chức năng, exposure, dữ liệu, test tối thiểu, feature flag, canary, monitoring, rollback và hạn sửa. Nếu có yêu cầu phát hành bắt buộc do hợp đồng/pháp luật hoặc chính sách không cho exception, release owner không thể tự cấp waiver trái quy định.

### 15.4. Patch exceptions và EOL systems

Với lỗ hổng chưa có patch hoặc hệ thống EOL, cần ghi advisory/CVE, đường khai thác, tình trạng vendor, biện pháp giảm phơi nhiễm, kiểm thử segmentation/WAF, dự án nâng cấp và giám sát CVE mới. Không cho phép gia hạn liên tục một hệ thống EOL mà không có review các phương án thay thế.

## 16. Metrics: Đo chương trình ngoại lệ nhưng không “tối ưu để đẹp số”

Chỉ số phải phản ánh phạm vi, trọng số rủi ro và chất lượng bằng chứng.

| Chỉ số | Ý nghĩa | Điều dễ hiểu sai |
|---|---|---|
| **Open exceptions by risk/severity** | Số ngoại lệ còn hiệu lực, theo tác động và yêu cầu nguồn. | Số thấp có thể do không phát hiện hoặc không ghi nhận, không hẳn kiểm soát tốt. |
| **Expired exceptions** | Số ngoại lệ quá hạn mà chưa có quyết định hợp lệ. | Không tính chỉ những ngoại lệ còn được lọc trên dashboard “active”. |
| **Median/percentile exception age** | Tuổi ngoại lệ từ lúc phát hiện/phê duyệt theo định nghĩa. | Cần phân biệt thời gian chưa phê duyệt và thời gian hiệu lực được phép. |
| **Compensating control verification** | Ngoại lệ áp dụng có biện pháp bù trừ được kiểm tra đạt trong kỳ / tổng ngoại lệ yêu cầu bù trừ. | Một test PASS trên mẫu nhỏ không chứng minh mọi asset cùng đáp ứng. |
| **Scope drift rate** | Tỷ lệ ngoại lệ có thay đổi asset/identity/data ngoài phạm vi đã duyệt. | Đòi nguồn inventory đầy đủ. |
| **Renewal rate và repeat exceptions** | Số lần gia hạn và các ngoại lệ cùng nguyên nhân liên tục tái diễn. | Gia hạn đúng thủ tục vẫn có thể cho thấy rủi ro tồn kéo dài. |
| **Remediation on-time closure** | Tỷ lệ khắc phục và retest đạt trước hạn. | Ticket đóng không đồng nghĩa control đạt. |
| **Evidence completeness** | Hồ sơ có requirement, scope, risk, approval, control test, expiry và monitoring. | Điền đủ ô không đồng nghĩa thông tin chính xác hoặc hợp lệ. |
| **Unapproved deviations** | Các tình trạng lệch phát hiện nhưng không có phê duyệt hợp lệ. | Không được che bằng cách ghi N/A hoặc xóa finding. |
| **Legal/contractual conflict cases** | Các trường hợp cần hành động bên ngoài quyền phê duyệt nội bộ. | Không gộp vào policy exception đã được duyệt. |

### 16.1. Ví dụ phép đo

Giả sử tổ chức có 30 ngoại lệ đang được theo dõi, trong đó 24 còn hạn, 4 đã quá hạn chưa được duyệt lại, 2 đang chờ quyết định. Trong 24 ngoại lệ còn hạn, 20 yêu cầu biện pháp bù trừ, nhưng chỉ 16 có kết quả test còn hiệu lực.

- **Hợp lệ về thời hạn:** 24/30 = 80% trên tổng danh mục đang theo dõi (chưa nói gì về kỹ thuật).
- **Quá hạn chưa giải quyết:** 4/30 ≈ 13,3%.
- **Kiểm chứng biện pháp bù trừ:** 16/20 = 80% trong tập yêu cầu kiểm tra (không tự suy ra “80% an toàn”).
- Hai request đang chờ **không phải** ngoại lệ được phê duyệt; phải quản lý trạng thái riêng.

Những con số là giả định và mẫu số phải được giải thích. Nếu có 10 deviation chưa từng được ghi vào hệ thống, tỷ lệ dựa trên 30 hồ sơ sẽ che một phần quan trọng của thực trạng.

### 16.2. Escalation khi số liệu tăng

Nhiều ngoại lệ lặp lại ở cùng một control thường chỉ ra **vấn đề thiết kế chương trình hoặc thiếu đầu tư**, không phải đơn thuần trách nhiệm của từng system owner. Có thể cần thay baseline, hỗ trợ migration, cải tiến quy trình mua sắm, sửa kiến trúc hoặc phân bổ nguồn lực thay vì chỉ yêu cầu các nhóm cập nhật ngày hết hạn.

## 17. Tình huống thực hành: Ngoại lệ MFA cho ứng dụng legacy

Một ngân hàng giả định quản lý hệ thống back-office cũ, truy cập thông qua máy chủ trung gian (bastion). Chính sách nội bộ yêu cầu MFA cho mọi tài khoản quản trị production. Ứng dụng legacy không hỗ trợ MFA native; nhóm vận hành xin ngoại lệ sáu tháng.

Thông tin ban đầu:

- Hai VM application chạy trong mạng nội bộ, nhưng một cổng quản trị trực tiếp vẫn mở từ subnet hỗ trợ.
- Bastion đã bật MFA cho nhân viên nội bộ, chưa kiểm tra tài khoản của nhà thầu.
- Audit log tại ứng dụng chỉ lưu 7 ngày; security policy yêu cầu kỳ lưu dài hơn.
- Nhóm vận hành dự kiến nâng cấp trong sáu tháng nhưng chưa có mốc release và người chịu trách nhiệm.
- Hệ thống xử lý dữ liệu khách hàng; bộ phận pháp lý chưa rà các yêu cầu hợp đồng liên quan.
- Service Owner đã ký “chấp nhận rủi ro” trong ticket, nhưng chính sách quy định risk owner cấp cao hơn duyệt ngoại lệ rủi ro cao.

### 17.1. Câu hỏi

1. Có thể coi ngoại lệ đã được phê duyệt hợp lệ chưa?
2. Biện pháp MFA tại bastion có bù trừ đủ khi còn cổng quản trị trực tiếp?
3. Cần kiểm tra những danh tính nào và những dữ liệu nào?
4. Yêu cầu logging bị thiếu có thể được gộp vào ngoại lệ MFA hay cần hồ sơ riêng?
5. Những bằng chứng và điều kiện nào cần có trước khi cho phép tiếp tục hoạt động có giới hạn?

### 17.2. Hướng giải

**Bước 1 — Xác định yêu cầu và thẩm quyền.** Đây là lệch control MFA nội bộ, nhưng còn cần kiểm tra nghĩa vụ hợp đồng/pháp luật cho dữ liệu khách hàng. Chữ ký của Service Owner chưa đủ vì ngoài thẩm quyền phê duyệt rủi ro cao theo chính sách; trạng thái request vẫn **PENDING/NOT AUTHORIZED** cho đến khi có quyết định đúng quyền.

**Bước 2 — Xác định scope đầy đủ.** Liệt kê hai VM, mọi tài khoản quản trị và service account có đường vào, account nhà thầu, IP/subnet nguồn, đường trực tiếp và đường bastion. Chỉ nói “hai VM nội bộ” chưa đủ vì subnet hỗ trợ có thể mở rộng và tài khoản đối tác có rủi ro khác.

**Bước 3 — Kiểm thử compensating controls.** Thử đăng nhập qua bastion (MFA bắt buộc), đường SSH/RDP trực tiếp bị từ chối, thời hạn phiên/JIT, access review và log tới kho tập trung. Cổng trực tiếp còn mở và nhà thầu chưa được kiểm tra => **chưa đạt các điều kiện bù trừ đề xuất**.

**Bước 4 — Tách findings.** Yêu cầu log retention là control khác; cần mở hoặc liên kết finding riêng với loại event, mức giữ, khả năng export và kiểm chứng end-to-end. Có thể dùng cùng kế hoạch khắc phục tổng thể, nhưng không tự động cấp waiver cho cả logging trong ngoại lệ MFA.

**Bước 5 — Hoàn thiện đánh giá rủi ro.** Xem dữ liệu, đường khai thác, nhà thầu, tài khoản có quyền cao, khả năng giám sát và mức độ phơi nhiễm. Yêu cầu Legal/Compliance xác nhận nghĩa vụ ngoài nội bộ trước khi đưa ra kết luận về quyền cho phép.

**Bước 6 — Phương án quản lý.** Đóng cổng trực tiếp, xác minh MFA cho mọi actor thuộc phạm vi, đưa log tới kho bảo vệ, đặt milestones và owner cho nâng cấp; sau đó gửi phê duyệt đúng thẩm quyền với hạn ngắn và trigger review. Nếu các điều kiện không thể đạt hoặc có nghĩa vụ không cho phép ngoại lệ, phải **giới hạn/dừng đường quản trị rủi ro hoặc thay phương án kỹ thuật**.

**Bước 7 — Retest và kết luận.** Dù ngoại lệ quản trị về sau đạt, control MFA native vẫn chưa đạt theo mục tiêu được định nghĩa; ghi riêng tình trạng control gốc, control bù trừ, phê duyệt và nghĩa vụ ngoài tổ chức. Chỉ đóng sau khi triển khai giải pháp đáp ứng control và kiểm thử không còn đường bypass.

### 17.3. Bảng kết luận tại thời điểm ban đầu

| Hạng mục | Bằng chứng ban đầu | Kết luận |
|---|---|---|
| Control MFA gốc | Ứng dụng không hỗ trợ MFA native | **FAIL** cho yêu cầu hiện tại. |
| Authorization | Service Owner chưa đủ quyền theo chính sách | **FAIL** về điều kiện phê duyệt nếu đang coi là active. |
| MFA qua bastion | Đã bật cho nhân viên; nhà thầu chưa kiểm tra | **INCONCLUSIVE** cho toàn bộ actor. |
| Chặn đường bypass | Cổng trực tiếp còn mở | **FAIL** đối với kiểm soát bù trừ. |
| Logging retention | Chỉ 7 ngày, không đáp ứng policy đã nêu | **FAIL** theo control logging, cần xử lý riêng. |
| Legal/contract applicability | Chưa rà soát | **INCONCLUSIVE**, chưa thể kết luận được quyền ngoại lệ. |
| Remediation timeline | Chưa có milestone/owner | **FAIL** đối với điều kiện kế hoạch khắc phục đầy đủ. |

**Kết luận:** Không thể gọi trường hợp này “compliant with exception” tại thời điểm ban đầu. Nếu vì tính thiết yếu nghiệp vụ vẫn cần truy cập để khắc phục, phải dùng cơ chế khẩn và điều kiện bảo vệ phù hợp theo thẩm quyền; không ký hậu kiểm giả để che việc truy cập ngoài phê duyệt.

## 18. Trường hợp đặc biệt: Nghĩa vụ không được phép “waive” nội bộ

Giả sử doanh nghiệp xử lý dữ liệu của khách hàng theo hợp đồng quy định một biện pháp bảo mật bắt buộc, không có điều khoản cho phép thay thế đơn phương. Đội kỹ thuật cho rằng biện pháp hiện tại khác nhưng “tương đương 90%” và trưởng bộ phận kỹ thuật duyệt ngoại lệ.

Điều cần xem xét:

1. **Contractual obligation:** cách diễn đạt, phạm vi, quyền sửa đổi, người có quyền chấp thuận và yêu cầu thông báo.
2. **Legal applicability:** luật bắt buộc nào áp dụng, có quy trình miễn trừ hợp lệ hay không; không suy đoán từ tên framework.
3. **Evidence of equivalence:** biện pháp thay thế giảm rủi ro ra sao; kết quả kiểm thử và giới hạn.
4. **Decision path:** đàm phán, bổ sung phụ lục hợp đồng hoặc thay thiết kế nếu được phép; không che sự khác biệt bằng ticket nội bộ.
5. **Reporting:** trong khi chưa giải quyết, báo trạng thái không phù hợp hoặc chưa đủ bằng chứng theo định nghĩa, phân công remediation và đánh giá tác động.

Trong ngữ cảnh GDPR, HIPAA, PCI DSS, tiêu chuẩn chứng nhận hoặc luật địa phương, **cơ chế sử dụng biện pháp thay thế và ngoại lệ rất khác nhau**. Không khẳng định mọi chuẩn cho phép “compensating control” theo cùng thủ tục, hay mọi nonconformity đều có thể giải quyết bằng chấp nhận rủi ro. Hãy đối chiếu phiên bản yêu cầu hiện hành và tư vấn chuyên môn phù hợp, tách kỹ thuật khỏi kết luận pháp lý.

## 19. Sai lầm phổ biến và cách phòng tránh

| Sai lầm | Hậu quả | Hướng khắc phục |
|---|---|---|
| Dùng ngoại lệ như một nhãn biến FAIL thành PASS. | Báo cáo assurance không còn trung thực. | Tách control effectiveness, exception governance và risk decision. |
| Phê duyệt nghĩa vụ bắt buộc bằng chữ ký nội bộ. | Rủi ro vi phạm pháp luật/hợp đồng vẫn tồn tại. | Kiểm tra applicability, thẩm quyền và cơ chế hợp lệ trước approval. |
| Ngoại lệ không giới hạn asset hoặc actor. | Phạm vi mở rộng âm thầm, khó giám sát. | Dùng asset IDs, identities, action, environment, data scope cụ thể. |
| Đặt hạn “cho đến khi có bản vá”. | Ngoại lệ kéo dài vô thời hạn. | Chốt expiry, milestones, trigger và escalation. |
| Cho phép một người tự phê duyệt mọi thứ. | Xung đột lợi ích và thiếu độc lập. | Tách quyền request, assess, risk accept và verify phù hợp. |
| Chỉ mô tả control bù trừ, không test. | Không biết có bypass hay không. | Test end-to-end, lưu raw evidence và retest định kỳ. |
| Nhầm detection với prevention tương đương. | Tấn công xảy ra trước khi alert được xử lý. | Đánh giá mục tiêu kiểm soát và khả năng giảm rủi ro còn lại. |
| Không theo dõi asset/config drift. | Tài sản mới nằm ngoài phê duyệt nhưng vẫn dùng waiver cũ. | Giám sát inventory, effective config và điều kiện kích hoạt review. |
| Gia hạn tự động vì đã được duyệt kỳ trước. | Không xét rủi ro mới và nguyên nhân chậm sửa. | Yêu cầu reassessment và phê duyệt lại dựa trên bằng chứng mới. |
| Ticket remediation đóng dù retest chưa đạt. | Root cause tồn tại, finding bị che. | Retest control gốc, owner khác xác nhận nếu cần. |
| Chỉ đếm ngoại lệ “active”, bỏ quá hạn. | Dashboard đẹp nhưng thiếu trung thực. | Báo tất cả trạng thái pending, denied, expired, revoked và closed. |
| Không lưu history hoặc approval version. | Không chứng minh được thời kỳ nào cho phép điều gì. | Immutable/versioned decision log, timestamps, audit trail. |
| Gộp policy, contract và legal exception. | Nhầm thẩm quyền và nghĩa vụ thông báo. | Phân loại nguồn yêu cầu, lập hồ sơ liên kết nhưng giữ outcome riêng. |
| Giữ ngoại lệ cho tài sản đã xóa mà không đối soát. | Danh mục sai và quyền tạm có thể còn. | Kiểm tra decommission, revoke quyền và đóng theo bằng chứng. |

## 20. Checklist đánh giá Exception compliance

Trước khi phê duyệt, gia hạn hoặc đóng một ngoại lệ, người làm security assurance cần xác minh:

1. **Yêu cầu gốc:** Có control/requirement ID, nguồn, phiên bản, ngày hiệu lực và tiêu chí cần đáp ứng không?
2. **Applicability:** Yêu cầu có áp dụng cho scope này không? Ngoại lệ có được phép theo chính sách, hợp đồng và luật không?
3. **Tình trạng thực tế:** Có phép kiểm tra và evidence cho lệch hiện tại, không dựa riêng vào mô tả của người đề nghị không?
4. **Phạm vi:** Asset, actor, region, môi trường, dữ liệu, đường truy cập và hành động được phép có giới hạn rõ không?
5. **Rủi ro:** Threat scenario, exposure, impact, dữ liệu và residual risk đã được đánh giá theo khung được duyệt chưa?
6. **Biện pháp bù trừ:** Có control ID, kết quả thử hiệu lực, giới hạn, chủ sở hữu và cơ chế theo dõi không?
7. **Thẩm quyền:** Người phê duyệt có đúng quyền, không xung đột vai trò; compliance/legal đã tham gia khi cần chưa?
8. **Thời gian:** Có ngày bắt đầu/hết hạn, mốc đánh giá, remediation deadline và người xử lý không?
9. **Giám sát:** Có phát hiện khi policy drift, tài sản mới, nguy cơ tăng, control bù trừ lỗi hoặc có incident không?
10. **Evidence:** Có nguồn, timestamp, scope, test procedure, artifact, reviewer, decision log và version phù hợp không?
11. **Kết luận:** Đã tách kết quả control gốc, governance ngoại lệ, compensating control và nghĩa vụ bên ngoài chưa?
12. **Gia hạn:** Có reassessment, bằng chứng mới, nguyên nhân chậm, phương án thay thế và quyết định đúng quyền không?
13. **Khắc phục:** Control gốc đã retest trên toàn bộ scope và finding đã đóng theo bằng chứng chưa?
14. **Lịch sử:** Các kỳ FAIL, thời hạn hết hiệu lực, ngoại lệ được duyệt và kết quả sau sửa có được bảo toàn không?
15. **Liên tục:** Có cơ chế đo coverage, overdue, repeat exceptions và cải tiến control/architecture để giảm nguyên nhân tái diễn không?

**Exception compliance có giá trị security assurance khi tổ chức không che khuất sự lệch khỏi yêu cầu, mà chứng minh được ranh giới cho phép, quyền quyết định, mức rủi ro, hiệu lực biện pháp bù trừ, kế hoạch khắc phục và trạng thái từng kỳ bằng bằng chứng có thể truy vết. Một ngoại lệ được quản trị tốt là ngoại lệ có điều kiện, có hạn và có đường kết thúc — không phải giấy phép bỏ qua tuân thủ vô thời hạn.**

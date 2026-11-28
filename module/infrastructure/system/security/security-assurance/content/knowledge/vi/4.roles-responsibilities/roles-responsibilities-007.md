# Developer: Vai trò và trách nhiệm trong Security Assurance

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nêu vai trò của **Developer (lập trình viên)** trong chương trình security assurance và phân biệt trách nhiệm của Developer với Tech Lead, Security/AppSec, nhóm vận hành, chủ sở hữu rủi ro và bộ phận audit.
- Chuyển kết quả phân tích rủi ro thành yêu cầu bảo mật, tiêu chí nghiệm thu, thiết kế security controls và trường hợp kiểm thử có thể đánh giá.
- Áp dụng các thực hành phát triển an toàn cho API và dịch vụ Java, đặc biệt ở các ranh giới tin cậy, xác thực, phân quyền, xử lý dữ liệu, bí mật và quản lý phụ thuộc.
- Thu thập **bằng chứng gắn với commit, build, kết quả kiểm thử và môi trường triển khai** để hỗ trợ khẳng định rằng control đang đáp ứng mục tiêu bảo mật.
- Phối hợp review, triage lỗ hổng, xử lý phát hiện từ audit và kiểm thử lại; nhận biết khi nào cần đánh giá lại kết luận assurance.

## 1. Developer đóng góp gì cho security assurance?

Trong nội dung **“Vai trò và trách nhiệm”** của module **SECURITY_SECURITY_ASSURANCE**, Developer là người trực tiếp biến nhiều yêu cầu bảo mật thành **hành vi thực thi của phần mềm** và cung cấp dữ liệu kỹ thuật để người có trách nhiệm đánh giá hành vi đó.

Security assurance là quá trình xây dựng cơ sở tin cậy, có thể kiểm chứng, rằng hệ thống đáp ứng các mục tiêu bảo mật trong phạm vi xác định. Quá trình này liên kết:

~~~mermaid
flowchart LR
    A["Rủi ro và tài sản"] --> B["Mục tiêu, yêu cầu bảo mật"]
    B --> C["Thiết kế và hiện thực security controls"]
    C --> D["Kiểm thử, review và thu thập bằng chứng"]
    D --> E["Đánh giá claim và phát hiện thiếu hụt"]
    E --> F["Khắc phục, retest và giám sát"]
    F --> C
~~~

Developer tham gia từ lúc phân tích rủi ro đến sau khi phát hành. Viết code không có lỗi là mục tiêu quá chung chung và không thể tự chứng minh. Một tuyên bố cụ thể hơn là: **“Ở build X của dịch vụ tài liệu, người dùng không thể đọc tài liệu thuộc người dùng khác qua bất kỳ endpoint đọc hoặc xuất dữ liệu nào trong phạm vi kiểm thử.”**

Developer có thể hỗ trợ tuyên bố này bằng mã kiểm tra quyền, review thay đổi, kết quả test tích cực/tiêu cực, định danh commit và build, cùng thông tin về đường triển khai. Kết luận cuối cùng cần nêu rõ phạm vi đã kiểm tra và những điểm chưa được chứng minh.

### Những việc Developer chịu trách nhiệm trực tiếp

| Nhóm hoạt động | Công việc cụ thể | Đầu ra có thể kiểm tra |
| --- | --- | --- |
| Xác định rủi ro | Xác định tài sản, luồng dữ liệu, ranh giới tin cậy, kịch bản lạm dụng | Threat model, abuse case, ghi chú quyết định thiết kế |
| Cụ thể hóa yêu cầu | Chuyển mục tiêu thành tiêu chí có thể test và nhận diện giới hạn | Security acceptance criteria, test scenario, liên kết risk/control |
| Thiết kế và phát triển | Hiện thực phân quyền, kiểm tra đầu vào, xử lý lỗi, bảo vệ dữ liệu và bí mật | Commit, code review, thiết kế API, cấu hình ứng dụng |
| Kiểm chứng | Viết và duy trì unit, integration, contract/security tests; đánh giá phát hiện công cụ | Test source, CI run, log kết quả, bản ghi triage |
| Phối hợp phát hành | Đối chiếu phiên bản đã kiểm thử với artifact được phát hành; làm rõ rủi ro tồn đọng | Build/image digest, release notes, xác nhận handoff |
| Khắc phục | Điều tra lỗi, sửa nguyên nhân, bổ sung regression test và retest | Finding, PR sửa, kết quả kiểm thử trước/sau |
| Vận hành và cải tiến | Hỗ trợ sự cố, bổ sung telemetry, sửa control khi có thay đổi hoặc evidence mất hiệu lực | Phân tích nguyên nhân, change record, cập nhật test và bằng chứng |

**Ranh giới quan trọng:** Developer có nghĩa vụ phát hiện, giải thích, khắc phục và báo cáo rủi ro liên quan sản phẩm. Developer **không tự động có thẩm quyền chấp nhận mọi rủi ro bảo mật**, tự đánh giá độc lập tất cả control do mình thực hiện hoặc một mình quyết định triển khai khi vượt ngưỡng chấp nhận của tổ chức.

## 2. Ranh giới vai trò và phối hợp với các nhóm

Việc phân vai cần dựa vào tổ chức thực tế, mức độ rủi ro và đặc điểm hệ thống. Một startup có thể giao nhiều trách nhiệm cho một người; tổ chức lớn có thể tách hẳn AppSec, SOC, IAM, Platform và Audit. Dù cấu trúc thế nào, mỗi quyết định quan trọng phải có người chịu trách nhiệm cuối cùng.

### Ma trận RACI minh họa

**R (Responsible):** trực tiếp thực hiện. **A (Accountable):** chịu trách nhiệm cuối cùng. **C (Consulted):** được tham vấn. **I (Informed):** được thông báo.

| Hoạt động | Developer | Tech Lead / Service Owner | Security / AppSec | Ops / SRE | Chủ sở hữu rủi ro | Audit |
| --- | --- | --- | --- | --- | --- | --- |
| Xây dựng tiêu chí bảo mật cho tính năng mới | **R** | C | C | C | **A** | I |
| Thiết kế và hiện thực control trong ứng dụng | **R** | **A** | C | C | I | I |
| Viết test bảo mật và xử lý kết quả CI của ứng dụng | **R** | **A** | C | C | I | I |
| Cấu hình control hạ tầng production | C | **A** | C | **R** | I | I |
| Điều tra và sửa lỗ hổng mã ứng dụng | **R** | **A** | C | C | I | I |
| Quyết định ngoại lệ chấp nhận rủi ro vượt ngưỡng | C | C | C | C | **R/A** | I |
| Thực hiện đánh giá hoặc audit độc lập | C | I | C | C | I | **R/A** |

Đây là mẫu để thảo luận, không phải cơ cấu bắt buộc. “Tech Lead / Service Owner” trong bảng là một vai trò trách nhiệm của dịch vụ; nếu được tách ra, phải chỉ định lại **A** cho từng hoạt động. Trong một quy trình cụ thể cần tránh tình trạng không ai là A hoặc nhiều người có thể phủ nhận trách nhiệm cuối cùng.

Ví dụ: Developer có thể được giao sửa kiểm tra quyền truy cập ở endpoint; AppSec hỗ trợ đánh giá threat model và test; Ops triển khai bản mới và xác minh cấu hình; Service Owner xác nhận mức độ hoàn tất; nếu cần chấp nhận rủi ro còn lại, quyết định phải đến người có thẩm quyền theo chính sách.

### Phân biệt ba loại bằng chứng

- **Bằng chứng thiết kế:** sơ đồ luồng dữ liệu, tài liệu ADR, threat model và tiêu chí nghiệm thu cho biết nhóm **dự định** bảo vệ gì.
- **Bằng chứng triển khai/kiểm thử:** code, cấu hình, unit/integration test, kết quả scan và review cho thấy một phiên bản **được hiện thực và đánh giá** ra sao.
- **Bằng chứng vận hành:** image đang chạy, cấu hình production, log và kiểm tra thực tế do Developer phối hợp với Ops thu thập để chứng minh control **có hiệu lực trên môi trường cụ thể**.

Không có loại nào tự động thay thế các loại còn lại.

## 3. Chuyển rủi ro thành yêu cầu có thể kiểm tra

Developer không nên nhận các yêu cầu mơ hồ như “API phải bảo mật” rồi đánh dấu hoàn thành khi đã thêm một middleware xác thực. Mỗi yêu cầu cần nêu **đối tượng cần bảo vệ, hành vi được phép, hành vi phải bị từ chối và cách xác minh**.

Giả sử hệ thống quản lý báo cáo tài chính có hai khách hàng doanh nghiệp (tenant) A và B. Người dùng thuộc tenant A biết ID của báo cáo tenant B và thử tải xuống qua API.

| Bước | Nội dung minh họa |
| --- | --- |
| **RISK-01** | Báo cáo nhạy cảm của tenant B bị lộ do API phân quyền theo role nhưng không giới hạn tenant. |
| **OBJ-01** | Bảo vệ tính bí mật và ranh giới dữ liệu giữa các tenant. |
| **REQ-01** | Mọi endpoint đọc/xuất báo cáo phải kiểm tra quyền trên **báo cáo đích và tenant của người yêu cầu**. |
| **CTRL-01** | Chính sách ủy quyền cấp đối tượng tại tầng dịch vụ, bảo đảm các luồng API dùng cùng nguồn quy tắc. |
| **TEST-01** | Kiểm tra owner, người được chia sẻ hợp lệ, user của tenant khác, user chưa đăng nhập, quyền vừa bị thu hồi. |
| **EV-01** | Commit, test suite, CI run, review và bằng chứng deployment tương ứng. |
| **FIND-01** | Nếu endpoint export bỏ qua kiểm tra quyền, ghi phát hiện và bổ sung kiểm chứng hồi quy. |

### Tiêu chí nghiệm thu nên viết như thế nào?

Ví dụ cho REQ-01:

1. User A đọc báo cáo của chính tenant A khi có quyền: thành công và chỉ trả dữ liệu trong phạm vi.
2. User A thử đọc/xuất báo cáo của tenant B: bị từ chối, **không trả nội dung nhạy cảm**.
3. API tải xuống, xem trước, export hàng loạt và các đường truy cập khác phải cùng tuân theo chính sách.
4. Khi quyền chia sẻ bị thu hồi, request mới không còn truy cập được theo yêu cầu nghiệp vụ.
5. Các tình huống lỗi hoặc không tìm thấy đối tượng không làm lộ nội dung hoặc metadata ngoài phạm vi được phép.
6. Bộ test chạy được trong CI và có thể liên kết kết quả với một commit/build xác định.

Tùy chính sách, hệ thống có thể trả HTTP 403 hoặc cố tình trả 404 để hạn chế tiết lộ sự tồn tại của đối tượng. **Mục tiêu kiểm chứng là không cung cấp dữ liệu trái phép** và tránh side channel phù hợp mô hình rủi ro, không mặc định một mã HTTP duy nhất là chính sách đúng cho mọi ứng dụng.

### Threat modeling từ góc nhìn Developer

Khi thiết kế tính năng, Developer phối hợp cùng Security và chủ sở hữu nghiệp vụ xác định:

- **Tài sản:** báo cáo, token, thông tin cá nhân, thao tác phê duyệt, dữ liệu lưu trữ.
- **Đầu vào và bên tham gia:** người dùng, service account, queue, webhook, đối tác, quản trị viên.
- **Ranh giới tin cậy:** Internet → gateway → service → database/object storage; service → API đối tác.
- **Khả năng của kẻ tấn công:** sửa ID, gửi payload tùy ý, dùng token bị đánh cắp, lặp request, gọi trực tiếp service nội bộ.
- **Kết quả xấu:** đọc sai tenant, thay đổi trái phép, mất dữ liệu, ghi log lộ secret hoặc gây gián đoạn.
- **Biện pháp giảm thiểu và bằng chứng:** authorization, validation, signing, rate limit, kiểm thử, cấu hình và telemetry.

Có thể dùng STRIDE, attack tree, abuse case hay phương pháp khác phù hợp; quan trọng là threat model dẫn đến **quyết định thiết kế và test cụ thể**. Threat model là tài liệu sống: khi thêm endpoint, trust boundary hoặc kiểu dữ liệu mới, Developer phải xem xét lại giả định.

## 4. Thiết kế và hiện thực security controls trong ứng dụng

Developer chịu trách nhiệm lựa chọn, triển khai và kiểm chứng control ứng dụng theo mức rủi ro. Những nhóm control thường cần chú ý:

| Chủ đề | Trách nhiệm của Developer | Cách kiểm chứng điển hình |
| --- | --- | --- |
| Xác thực và quản lý phiên | Dùng cơ chế xác thực phù hợp, kiểm tra token/session đúng ngữ cảnh, không tự phát minh giao thức | Test phiên hết hạn, token không hợp lệ, trạng thái đăng xuất/thu hồi |
| Phân quyền | Kiểm tra quyền tại đối tượng và hành động cụ thể; nguyên tắc deny by default | Positive/negative tests theo role, tenant, resource và đường truy cập |
| Kiểm tra dữ liệu đầu vào | Kiểm tra cấu trúc, kích thước, định dạng, giới hạn nghiệp vụ; xử lý lỗi an toàn | Fuzz/boundary tests và test dữ liệu không hợp lệ |
| Chống injection | Dùng truy vấn tham số hóa, API an toàn cho command/path/template | Test các input đặc biệt, review đường ghép chuỗi nguy hiểm |
| Bảo vệ dữ liệu đầu ra | Encode theo ngữ cảnh HTML/JavaScript/URL, kiểm soát dữ liệu trả về, tránh log bí mật | Test XSS, data exposure, serializer và DTO |
| Mật mã | Sử dụng thư viện và thuật toán được duyệt, quản lý khóa/nonce đúng cách, không tự viết primitive | Review thiết kế, negative tests, kiểm tra vòng đời khóa |
| Tương tác hệ thống ngoài | Kiểm tra URL đích, quyền kết nối, chữ ký webhook và chống phát lại theo mô hình đe dọa | Test giả mạo webhook, truy cập địa chỉ không được phép, replay |
| Xử lý lỗi và logging | Lỗi cho người dùng không rò rỉ stack trace/secret; log đủ để điều tra và tuân thủ bảo vệ dữ liệu | Test response lỗi, redaction, correlation ID và audit event |
| Phụ thuộc và cấu hình | Quản lý version, quét dependency, cập nhật runtime/library và cấu hình an toàn | SCA, inventory/SBOM khi phù hợp, scan và kiểm tra artifact phát hành |

Không phải mọi security control đều nằm trong code. Ví dụ, TLS termination hoặc IAM của cloud có thể do Ops quản lý, nhưng Developer vẫn phải hiểu giả định tin cậy và **không tin một header “user-id” do client tự cung cấp** chỉ vì hạ tầng phía trước có gateway.

### Ví dụ Java/Spring Boot: phân quyền theo đối tượng

Với endpoint `GET /api/reports/{id}`, một thiết kế dễ sai là chỉ xác minh người dùng đã đăng nhập và có role `USER`, sau đó truy vấn báo cáo bằng ID người dùng gửi lên.

Ví dụ **minh họa** chuyển kiểm tra quyền vào tầng service để nhiều đường gọi có thể tái sử dụng:

~~~java
@Service
class ReportService {
    private final ReportRepository reports;
    private final ReportPolicy policy;

    ReportService(ReportRepository reports, ReportPolicy policy) {
        this.reports = reports;
        this.policy = policy;
    }

    ReportDto read(UUID reportId, Authentication actor) {
        Report report = reports.findById(reportId)
                .orElseThrow(() ->
                        new ResponseStatusException(HttpStatus.NOT_FOUND));

        if (!policy.canRead(actor, report)) {
            throw new AccessDeniedException("Access denied");
        }

        return ReportDto.from(report);
    }
}
~~~

`ReportPolicy.canRead(...)` là chính sách do ứng dụng triển khai: kiểm tra actor đã xác thực, vai trò phù hợp, tenant của báo cáo, quyền chia sẻ và các điều kiện nghiệp vụ cần thiết. Các lớp `ReportRepository`, `ReportPolicy` và `ReportDto` là thành phần minh họa, phải được hiện thực đầy đủ trong ứng dụng thật.

**Điều cần bảo đảm:** mọi đường truy cập báo cáo, kể cả export và batch job, đều đi qua cơ chế cấp quyền phù hợp; không có endpoint khác đọc thẳng repository rồi bỏ qua policy. Với tải dữ liệu quy mô lớn, cân nhắc giới hạn truy vấn theo tenant tại tầng lưu trữ để giảm cơ hội vượt ranh giới quyền. Trong một số trường hợp, cần tránh trả khác biệt về thông tin tồn tại của đối tượng ngoài phạm vi.

Bài kiểm thử tích hợp với Spring Security có thể minh họa trường hợp cross-tenant:

~~~java
@Test
@WithMockUser(username = "alice")
void cannotReadReportFromAnotherTenant() throws Exception {
    mockMvc.perform(get("/api/reports/{id}", tenantBReportId))
            .andExpect(status().isForbidden());
}
~~~

Để test trên đáng tin, fixture phải thực sự có báo cáo thuộc tenant B, identity Alice thuộc tenant A, `MockMvc` chạy với security filter và route thực tế gọi đúng `ReportService`. Thêm test được phép, không đăng nhập, quyền bị thu hồi và các API export. Một test có tên “cannotRead” nhưng mock trả HTTP 403 không chứng minh authorization thật đã hoạt động.

## 5. Kiểm thử bảo mật là trách nhiệm phát triển thường xuyên

Security tests cần kiểm tra **hành vi dự kiến và hành vi bị cấm**, không chỉ phản hồi “happy path”.

| Nhóm test | Điều cần kiểm chứng | Bằng chứng nên giữ |
| --- | --- | --- |
| Unit test chính sách | Quyết định cho phép/từ chối đúng với actor, resource và action | Source test, đầu vào/expected result, CI job |
| Integration test | Security filter, controller, service và kho dữ liệu áp dụng cùng chính sách | Test fixture, kết quả chạy trên môi trường xác định |
| Negative/abuse test | Tenant khác, ID đoán được, token lỗi, payload bất thường, thao tác vượt quyền | Test case lỗi, kết quả reject và sự kiện ghi nhận |
| Regression test | Lỗi đã từng phát hiện không xuất hiện lại sau khi sửa | Test tái hiện lỗi, commit sửa, kết quả trước/sau |
| Static code analysis (SAST) | Các pattern mã có thể dẫn đến lỗ hổng | Phiên bản rule/tool, finding, triage và quyết định sửa |
| Software composition analysis (SCA) | Thư viện có advisory lỗ hổng và phạm vi ảnh hưởng | Danh sách dependency, phiên bản, bản ghi xử lý |
| Dynamic/application test | Hành vi triển khai khi thực sự chạy, nơi có thể kiểm thử an toàn | Phạm vi môi trường, phương pháp, kết quả, giới hạn |

**Báo cáo không có phát hiện không đồng nghĩa hệ thống không có lỗ hổng.** Công cụ có phạm vi và hạn chế; một lỗ hổng logic phân quyền có thể hoàn toàn nằm ngoài rule của SAST/SCA. Cũng không nên xử lý các cảnh báo công cụ một cách máy móc: cần triage theo tính khai thác thực tế, dữ liệu và tài sản bị ảnh hưởng, đồng thời lưu lý do đánh giá false positive nếu có.

### Mẫu tiêu chí cho bài test security

~~~gherkin
Feature: Cô lập báo cáo giữa các tenant

  Scenario: Người dùng không được đọc báo cáo của tenant khác
    Given Alice đã xác thực và thuộc tenant A
    And báo cáo R-42 chỉ thuộc tenant B
    When Alice yêu cầu đọc báo cáo R-42 qua API
    Then hệ thống không trả nội dung báo cáo
    And yêu cầu bị từ chối theo chính sách
    And sự kiện phù hợp được ghi nhận mà không rò rỉ dữ liệu nhạy cảm

  Scenario: Người dùng có quyền đọc báo cáo hợp lệ
    Given Bob thuộc tenant B và có quyền đọc báo cáo R-42
    When Bob yêu cầu đọc báo cáo R-42
    Then hệ thống trả đúng nội dung được phép
~~~

Gherkin là **đặc tả mong đợi**, chưa phải bằng chứng test đã chạy. Developer cần chuyển các tình huống thành test tự động hoặc thực hiện kiểm thử có kiểm soát, lưu kết quả chạy gắn với phiên bản.

## 6. Code review và kiểm soát thay đổi

Review bảo mật không nên trở thành thao tác kiểm tra hình thức “đã có ít nhất một người approve”. Reviewer cần hiểu **security impact** của thay đổi và có căn cứ để kết luận.

Một pull request thay đổi tính năng nhạy cảm nên có:

1. **Mô tả hành vi:** endpoint, dữ liệu, actor, trust boundary và mục tiêu nghiệp vụ bị ảnh hưởng.
2. **Liên kết yêu cầu và rủi ro:** ví dụ `REQ-01`, issue, threat model/ADR liên quan.
3. **Phần thay đổi control:** xác thực, phân quyền, input validation, logic mã hóa, logging, quyền gọi service khác.
4. **Test có ý nghĩa:** kết quả positive và negative; test tái hiện lỗi cũ nếu sửa lỗ hổng.
5. **Tác động triển khai:** schema migration, phiên bản dependency, secret/config, quyền IAM cần thay đổi, ảnh hưởng đến log/backup.
6. **Khoảng trống và phương án theo dõi:** phần chưa kiểm thử, giới hạn môi trường, rủi ro có thể cần Security/Service Owner xem xét.

Ví dụ, nếu pull request bổ sung endpoint `GET /api/reports/export/{id}` nhưng chỉ test người sở hữu báo cáo xuất thành công, reviewer cần yêu cầu thêm ca **tenant khác không xuất được**, và xác minh endpoint mới không tạo đường truy cập bypass.

Developer không được coi việc “merge thành công” là bằng chứng rằng mọi mục tiêu bảo mật đã đạt. Một review giúp giảm rủi ro nhưng không thay kiểm thử thực thi hoặc xác nhận cấu hình production.

## 7. Trách nhiệm với dependency, supply chain và CI/CD

Phụ thuộc phần mềm, công cụ build, package và artifact là nguồn rủi ro đáng kể. Developer cần phối hợp cùng nhóm nền tảng để quản lý các mắt xích mà code có thể bị đưa vào hoặc biến đổi.

~~~mermaid
flowchart LR
    S["Source + dependency"] --> R["Review và kiểm tra nguồn"]
    R --> B["Build có danh tính, cấu hình được quản lý"]
    B --> T["Security tests và triage phát hiện"]
    T --> A["Artifact/image digest"]
    A --> D["Deploy có phê duyệt, kiểm chứng môi trường"]
    D --> O["Giám sát và đánh giá lại control"]
~~~

Các thực hành có giá trị gồm:

- Quản lý version dependency và nguồn tải; xem xét rủi ro package mới, plugin build, artifact không tin cậy và phụ thuộc đã không còn được duy trì.
- Dùng SCA và theo dõi advisory ảnh hưởng tới phiên bản đang sử dụng; đánh giá **khả năng bị ảnh hưởng thực tế** theo đường gọi và môi trường thay vì chỉ đếm số cảnh báo.
- Không đưa khóa bí mật, password hoặc token vào repository, test fixture, output build; bật secret scanning và quy trình thu hồi khi nghi ngờ lộ.
- Khi phù hợp, tạo danh mục thành phần phần mềm (SBOM), lưu định danh artifact và thông tin nguồn gốc build để truy vết được bản nào chứa dependency nào.
- Định nghĩa security checks trong pipeline; kết quả thất bại phải được xử lý theo quy trình, không tự ý tắt gate mà không được review.
- Khi cần sửa lỗ hổng library, bổ sung test tương thích và đối chiếu image/artifact đang chạy sau khi triển khai.

**Bằng chứng CI chỉ đại diện cho commit, cấu hình và môi trường của lần chạy đó.** Nếu release sử dụng image khác với image đã kiểm tra, hoặc production thay đổi cấu hình ngoài pipeline, kết luận phải được xem xét lại. Developer cần cung cấp commit/build/digest cho Ops và phối hợp xác minh khi có control liên quan môi trường chạy.

## 8. Developer tạo bằng chứng cho security assurance như thế nào?

Bằng chứng phục vụ một **claim** cụ thể và đủ dữ liệu để người khác xác minh. Nhìn thấy một dấu tích xanh trên màn hình CI không giúp assessor biết chính xác bài test nào đã chạy, trên commit nào hay bao phủ rủi ro gì.

### Chuỗi truy vết minh họa

~~~text
RISK-01: Lộ báo cáo giữa các tenant
  -> OBJ-01: Bảo vệ bí mật thông tin
  -> REQ-01: Kiểm tra quyền cấp đối tượng ở mọi luồng đọc/xuất
  -> CTRL-01: Policy ủy quyền trong ReportService
  -> TEST-01: Integration tests cross-tenant và export
  -> EV-01: Test result + commit + build + review + deployment
  -> CLAIM-01: Control đáp ứng phạm vi đã đánh giá
~~~

### Mẫu hồ sơ bằng chứng

Mẫu dưới đây là **cấu trúc tham khảo**, giá trị trong dấu `<...>` phải thay bằng hiện vật thật. Không thể coi bản mẫu là bằng chứng đã kiểm chứng.

~~~yaml
evidence_id: EV-DEV-001
claim_id: CLAIM-01
risk_id: RISK-01
requirement_id: REQ-01
control_id: CTRL-01
system: report-service
assessor_scope: "API đọc và xuất báo cáo theo tenant"
source_commit: "<GIT_COMMIT_SHA>"
build_id: "<CI_BUILD_ID>"
artifact_digest: "<IMAGE_OR_ARTIFACT_DIGEST>"
environment: "<TEST_ENVIRONMENT>"
test_suite: "<TEST_SUITE_NAME>"
test_run: "<CI_RUN_REFERENCE>"
observed_at: "<ISO_8601_UTC>"
result: "<PASS_FAIL_INCONCLUSIVE>"
review_record: "<PULL_REQUEST_OR_REVIEW_ID>"
deployment_reference: "<PRODUCTION_DEPLOYMENT_IF_VERIFIED>"
evidence_artifacts:
  - "<TEST_RESULT_URI>"
  - "<REVIEW_URI>"
  - "<CONFIGURATION_OR_RUNTIME_CHECK_URI>"
limitations: "<UNTESTED_PATHS_OR_ENVIRONMENT_GAPS>"
owner: "<DEVELOPER_OR_TEAM>"
reviewer: "<AUTHORIZED_REVIEWER>"
reassessment_trigger: "<CHANGE_OR_EXPIRY_CONDITION>"
~~~

Một bằng chứng có chất lượng cần:

| Tiêu chí | Câu hỏi Developer cần trả lời |
| --- | --- |
| **Liên quan** | Test/hiện vật có chứng minh đúng yêu cầu được gắn ID không? |
| **Bao phủ** | Tất cả đường truy cập, loại actor và tình huống rủi ro quan trọng đã được kiểm tra chưa? |
| **Nguồn gốc** | Có biết ai/công cụ nào tạo hiện vật, với code, dữ liệu và cấu hình nào không? |
| **Tính toàn vẹn** | Có thể nhận ra việc chỉnh sửa artifact hoặc tráo kết quả không? Nơi lưu có quản lý quyền, lịch sử thay đổi không? |
| **Thời điểm và hiệu lực** | Kết quả có còn đại diện cho phiên bản hiện tại và môi trường cần kết luận không? |
| **Khả năng tái lập** | Người review có đủ thông tin để chạy lại hoặc đối chiếu theo phương pháp đã mô tả không? |
| **Giới hạn** | Có minh bạch điểm chưa test, môi trường khác biệt, giả định hoặc rủi ro tồn dư không? |

Bằng chứng thường được tổng hợp tự động từ CI/CD, công cụ quản lý ticket và kết quả thử nghiệm. Nhưng người chịu trách nhiệm phải **diễn giải** ý nghĩa bằng chứng: ví dụ một unit test đạt giúp chứng minh policy method trong điều kiện giả lập, chưa chứng minh cấu hình xác thực thật hoặc phiên bản production được bảo vệ.

### Bản ghi finding và retest

Khi một bài test phát hiện export API cho phép truy cập khác tenant:

~~~yaml
finding_id: FIND-DEV-007
related_requirement: REQ-01
detected_in: "<BUILD_ID>"
affected_entry_point: "GET /api/reports/export/{id}"
reproduction: "<SANITIZED_TEST_CASE_OR_REFERENCE>"
impact: "Có khả năng đọc báo cáo ngoài tenant được phép"
owner: "<RESPONSIBLE_TEAM>"
remediation_commit: "<FIX_COMMIT>"
regression_test: "<TEST_CASE_ID>"
retest_run: "<RETEST_CI_RUN_ID>"
production_verification: "<DEPLOYMENT_AND_RUNTIME_CHECK>"
status: "<OPEN_IN_PROGRESS_VERIFIED>"
residual_risk: "<LIMITATIONS_AND_RISK_OWNER_DECISION>"
~~~

**Ticket được đóng không tương đương lỗ hổng đã được khắc phục.** Kết luận “đã sửa” cần gắn với bản vá, kết quả test hồi quy và trạng thái bản đã triển khai nếu rủi ro tồn tại trên production.

## 9. Phát hiện, phân loại và xử lý lỗ hổng

Không phải mọi cảnh báo đều có cùng mức độ ưu tiên. Developer phối hợp Security, chủ sở hữu hệ thống và Ops xác định:

- **Đúng hay sai?** Có thể tái hiện bằng input và môi trường phù hợp không; báo cáo chỉ là false positive hay thật sự có đường khai thác?
- **Phạm vi:** ứng dụng, phiên bản, tenant, chức năng, dữ liệu, role, môi trường và dependency nào bị ảnh hưởng?
- **Khả năng khai thác:** có cần xác thực/đặc quyền, điều kiện tiên quyết, tương tác người dùng hay không?
- **Tác động:** rò dữ liệu, sửa trái phép, phá vỡ availability, vượt quyền, ảnh hưởng chuỗi cung ứng hoặc tuân thủ?
- **Biện pháp tạm thời:** có thể giảm thiểu bằng cấu hình, chặn tính năng, giới hạn quyền hay giám sát bổ sung trong lúc chờ sửa?
- **Thẩm quyền:** việc trì hoãn/ngoại lệ có nằm trong chính sách không và ai được chấp nhận rủi ro tồn dư?

### Quy trình khắc phục có thể kiểm tra

1. **Tiếp nhận:** lưu finding với bằng chứng đã làm sạch thông tin nhạy cảm, cách tái hiện, môi trường, phiên bản và đường ảnh hưởng.
2. **Triage:** xác nhận tính hợp lệ, ưu tiên xử lý dựa trên rủi ro; nếu có nghi vấn sự cố thực tế, kích hoạt quy trình ứng cứu.
3. **Sửa nguyên nhân:** thay đổi thiết kế/code/cấu hình cần thiết, tránh chỉ che lỗi bằng thông báo trả về khác.
4. **Bổ sung regression test:** bài test tái hiện được trường hợp sai và bảo đảm đường hợp lệ vẫn hoạt động.
5. **Review:** người có năng lực kiểm tra sửa lỗi, ảnh hưởng đến các endpoint tương tự và nguy cơ phát sinh lỗ hổng mới.
6. **Retest và đối chiếu release:** lưu kết quả kiểm thử trên bản sửa, deployment ID và xác minh phạm vi runtime khi cần.
7. **Đóng có căn cứ:** cập nhật kết luận, bằng chứng, người xác nhận và các giới hạn; theo dõi rủi ro tồn đọng hoặc ngoại lệ.

Developer có thể đề xuất biện pháp và trình bày trade-off. **Quyết định chấp nhận rủi ro** thuộc vai trò được trao thẩm quyền, có hồ sơ nêu lý do, phạm vi, thời hạn, control bù trừ và điều kiện đánh giá lại. Không được đánh dấu control “PASS” chỉ vì ngoại lệ đã được phê duyệt.

## 10. Trách nhiệm trước và sau khi triển khai

### Trước release

Developer cần phối hợp đảm bảo các yêu cầu bảo mật áp dụng đã có tiêu chí nghiệm thu và kết quả đánh giá phù hợp. Ví dụ:

- Code, migrations, config và dependency thay đổi đã được review.
- Test security bắt buộc đã chạy trên commit/artifact phát hành; thất bại có xử lý rõ.
- Các đường truy cập mới đã được review authorization và tenant isolation.
- Đã thống nhất giá trị cấu hình/secret/permission cần thiết với Ops; không tự mở quyền rộng để “fix nhanh”.
- Finding nghiêm trọng chưa xử lý đã được nêu rõ cùng quyết định có thẩm quyền.
- Có plan rollback và khả năng quan sát tối thiểu để phát hiện control không vận hành đúng.

### Sau release

Developer không thể suy ra từ CI rằng production đã triển khai đúng. Cần phối hợp Ops/SRE để xác nhận **artifact digest và cấu hình thực tế**, thực hiện kiểm tra có kiểm soát trong phạm vi production nếu chính sách cho phép, và theo dõi metric/log/cảnh báo phù hợp.

Một thay đổi feature flag, tenant policy, identity provider hoặc sơ đồ kết nối có thể làm thay đổi điều kiện bảo mật ngay cả khi code không đổi. Khi xảy ra thay đổi ảnh hưởng control, Developer cần đánh giá lại claim và test liên quan.

### Khi có sự cố

Developer cung cấp kiến thức mã nguồn, truy vấn, dependency, đường dữ liệu và khả năng tái hiện cho nhóm ứng cứu. Những thao tác như thêm logging, thu hồi token, sửa khẩn hoặc rollback phải theo điều phối để cân bằng giảm thiểu ảnh hưởng và bảo quản bằng chứng. Không nên ghi secret hoặc dữ liệu người dùng nguyên bản vào log chỉ để điều tra cho nhanh.

Sau sự cố, Developer phân tích nguyên nhân kỹ thuật, bổ sung regression test, đánh giá các vị trí có cùng lớp lỗi và đóng góp tài liệu hậu kiểm. “Hệ thống đã chạy lại” chưa chứng minh nguyên nhân bảo mật đã được khắc phục.

## 11. Làm việc với audit và nhóm đánh giá

Assessor/auditor cần **đối chiếu hiện vật với claim**, vì vậy Developer phải có khả năng giải thích:

1. **Control nào nằm trong code?** Vị trí thực thi, các đường gọi, quyền, điều kiện và điểm giới hạn.
2. **Yêu cầu nào được kiểm tra?** ID yêu cầu, trường hợp test và điều kiện thành công/thất bại.
3. **Dữ liệu bằng chứng đến từ đâu?** CI run, scan report, repository commit, artifact và cấu hình tương ứng.
4. **Ai đã review?** PR, người duyệt, phạm vi review, các thay đổi sau lần review.
5. **Điều gì chưa được chứng minh?** Ví dụ test chỉ có môi trường staging, chưa bao phủ service callback hoặc chưa đối chiếu production.
6. **Finding được xử lý thế nào?** Mức ưu tiên, bản sửa, retest, kiểm tra deployment và phần rủi ro còn lại.

Developer cần minh bạch giới hạn của bằng chứng. Một kết quả `SAST: 0 high findings` không chứng minh mã không có lỗ hổng; một report penetration test được thực hiện trên version trước không chứng minh release hiện tại. Việc đánh giá độc lập phải được thực hiện bởi vai trò được chỉ định theo cơ chế quản trị, không chỉ dựa trên tự xác nhận của nhóm phát triển.

## 12. Kịch bản end-to-end: lỗi xuất báo cáo sai tenant

**Bối cảnh:** một dịch vụ Java/Spring Boot đã kiểm tra phân quyền khi xem báo cáo ở màn hình web. Một Developer mới thêm endpoint `/api/reports/export/{id}` để tải CSV. Endpoint mới chỉ kiểm tra role `USER`, sau đó lấy dữ liệu theo report ID. Người dùng tenant A có thể suy đoán một ID thuộc tenant B và tải tệp CSV.

### Đánh giá bằng chứng ban đầu

| Hiện vật | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| CI xanh sau PR | Các job được cấu hình đã chạy thành công trên commit liên quan | Chưa rõ security test có bao phủ export API hay không |
| Có annotation kiểm tra `USER` | Có điều kiện role tại một điểm code | Role cho phép có thể vẫn truy cập báo cáo ngoài tenant |
| Người dùng tenant A xem báo cáo A được | Đường hợp lệ hoạt động | Đường bất hợp lệ đã bị từ chối |
| Log ghi `export succeeded` | Hệ thống ghi nhận một lượt xuất báo cáo | Lượt xuất có được cấp quyền đúng và đủ hay không |

### Hành động của Developer

**Bước 1 — Tái hiện có kiểm soát.** Dùng tenant A và B giả lập, tài khoản không có quyền và báo cáo chứa dữ liệu thử. Ghi request/response đã được làm sạch, version ứng dụng và kết quả thực tế. Không truy cập dữ liệu khách hàng thật để tìm bằng chứng.

**Bước 2 — Xác định nguyên nhân.** Tìm đường export gọi thẳng repository, trong khi đường read dùng `ReportPolicy.canRead`. Kiểm tra các endpoint batch, download link, preview và các callback liên quan xem có cùng lỗi bỏ qua kiểm tra quyền hay không.

**Bước 3 — Sửa control.** Đưa export đi qua cùng cơ chế authorization cấp đối tượng và giới hạn tenant; kiểm tra bảo vệ từ lúc tạo link đến lúc tải dữ liệu nếu có URL tạm thời. Thêm kiểm thử cho authorized, unauthorized, cross-tenant, quyền bị thu hồi và đường có thể bị replay theo chính sách.

**Bước 4 — Kiểm chứng kỹ thuật.** Regression test với payload giống trường hợp ban đầu phải từ chối; các request hợp lệ tiếp tục thành công. PR được review; lưu commit, build, test suite và kết quả SAST/SCA liên quan.

**Bước 5 — Bàn giao triển khai.** Phối hợp Ops đối chiếu image digest và rollout; thử nghiệm có kiểm soát ở môi trường đích nếu được phép. Cùng Security rà soát log để xác định có dấu hiệu khai thác trước sửa và đánh giá phạm vi ảnh hưởng.

**Bước 6 — Đóng finding.** Ghi nhận test trước/sau, thời điểm và bản sửa đã chạy, người review, rủi ro tồn dư và trigger đánh giá lại. Không kết luận toàn hệ thống “an toàn tuyệt đối” chỉ vì một luồng export đã được sửa.

### Bộ evidence tối thiểu cho tình huống

| ID | Hiện vật | Chủ thể cung cấp | Mục đích |
| --- | --- | --- | --- |
| EV-D1 | Test tái hiện cross-tenant trên build lỗi | Developer | Chứng minh hành vi vi phạm |
| EV-D2 | PR, diff và review chính sách phân quyền | Developer/Reviewer | Chứng minh thay đổi control |
| EV-D3 | Positive/negative integration tests trên build sửa | Developer/CI | Chứng minh behavior đã thay đổi |
| EV-D4 | Artifact digest và trạng thái deployment | Ops phối hợp Developer | Kết nối bằng chứng test với môi trường đích |
| EV-D5 | Audit record và phân tích phạm vi ảnh hưởng | Security/Ops với hỗ trợ Developer | Xác định rủi ro trước sửa |
| EV-D6 | Kết luận retest và người phê duyệt đóng finding | Người đánh giá được giao | Chốt trạng thái có căn cứ |

## 13. Chỉ số và lịch hoạt động của Developer

Để assurance liên tục có thể quản trị, nhóm phát triển nên đưa các hoạt động vào quy trình phát triển thay vì chờ đến ngày audit.

| Điểm kích hoạt | Hoạt động Developer | Bằng chứng |
| --- | --- | --- |
| Thiết kế tính năng nhạy cảm | Cập nhật risk/abuse case, yêu cầu và threat model | Ticket, ADR, traceability |
| Mỗi pull request ảnh hưởng control | Review security impact, chạy test, đánh giá kết quả công cụ | Diff, approval, kết quả CI |
| Cập nhật dependency/runtime | Triage advisory và ảnh hưởng compatibility/security | SCA finding, thử nghiệm, quyết định cập nhật |
| Trước release | Xác nhận acceptance criteria, test, artifact và risk tồn đọng | Build ID, digest, release checklist |
| Khi phát hiện lỗ hổng | Tái hiện, sửa, regression test, review và handoff | Finding, remediation PR, retest |
| Sau sự cố hoặc thay đổi trust boundary | Phân tích nguyên nhân, cập nhật control và bằng chứng | Post-incident review, test, threat model mới |
| Theo chu kỳ do tổ chức quy định | Rà soát test bị bỏ qua, control còn thiếu evidence hoặc sắp hết hiệu lực | Evidence register, backlog và owner |

Một số chỉ số hữu ích: tỷ lệ yêu cầu rủi ro cao có negative tests được chạy, thời gian sửa finding theo mức độ rủi ro, tỷ lệ lỗ hổng được kiểm chứng lại trên bản đã triển khai, số control không có bằng chứng còn hiệu lực, tỷ lệ dependency quan trọng đã được đánh giá.

**Không chỉ tối ưu các con số dễ báo cáo.** Ví dụ, tăng số lượng test vô nghĩa hoặc đóng finding hàng loạt có thể làm dashboard đẹp hơn mà không cải thiện bảo mật. Chỉ số phải được đặt trong ngữ cảnh phạm vi, chất lượng test, hiệu lực control và rủi ro thực tế.

## 14. Những nhầm lẫn thường gặp

| Nhận định sai | Vì sao sai? | Cách thực hành tốt hơn |
| --- | --- | --- |
| “Bảo mật là việc của Security Team.” | Code, API và dữ liệu do Developer thiết kế có thể tạo lỗ hổng trực tiếp. | Developer sở hữu các control ứng dụng được giao và phối hợp review chuyên môn. |
| “Có authentication là đủ.” | Người dùng đã đăng nhập vẫn có thể vượt quyền vào đối tượng khác. | Kiểm tra authorization trên resource/action, test cả truy cập trái phép. |
| “Có unit test đạt là production an toàn.” | Unit test thường mock nhiều thành phần; production còn cấu hình và artifact khác biệt. | Test tích hợp và đối chiếu version/deployment. |
| “Không có cảnh báo SAST thì không có lỗi.” | SAST không chứng minh logic nghiệp vụ và quyền truy cập luôn đúng. | Kết hợp threat model, review và behavioral security tests. |
| “Chỉ cần sửa code, Ops sẽ tự biết.” | Bản sửa có thể chưa triển khai hoặc cần thay đổi quyền, schema, secret và runbook. | Handoff rõ tác động và cách kiểm chứng sau release. |
| “Ticket đóng nghĩa là security finding đã hết.” | Chưa có bằng chứng retest và triển khai. | Gắn closing criteria với test, build và môi trường thực. |
| “Developer có thể tự chấp nhận rủi ro để release nhanh.” | Quyền quyết định phụ thuộc cơ chế quản trị và mức độ rủi ro. | Trình phương án, bằng chứng và giới hạn cho đúng người phê duyệt. |
| “Evidence là screenshot CI xanh.” | Thiếu nguồn gốc, phạm vi, điều kiện và liên kết với yêu cầu. | Lưu báo cáo có định danh, phiên bản, test case, thời điểm và reviewer. |

## 15. Bài tập ứng dụng

**Tình huống:** một nhóm phát triển cung cấp tính năng thay đổi thông tin người nhận tiền. Story có yêu cầu “người dùng phải đăng nhập”. Sau release, nhóm đánh giá phát hiện người dùng A có thể sửa thông tin của người dùng B bằng cách thay `recipientId` trong JSON. Developer cho biết endpoint có dùng JWT và toàn bộ test đều PASS.

Hãy giải quyết:

1. Những mục tiêu bảo mật nào đã bị ảnh hưởng? Vì sao JWT hợp lệ không đủ chứng minh quyền sửa `recipientId`?
2. Viết lại ít nhất **hai yêu cầu bảo mật có thể kiểm thử** và các ca negative test tương ứng.
3. Phân công trách nhiệm Developer, Tech Lead, Security, Ops và chủ sở hữu rủi ro trong xử lý.
4. Liệt kê bằng chứng cần thu thập để chứng minh bản sửa đã có hiệu lực ở production.
5. Nếu chưa thể vá trong cùng ngày, ai có thể quyết định dùng biện pháp giảm thiểu/ngoại lệ? Hồ sơ cần chứa gì?

### Hướng dẫn trả lời

| Câu hỏi | Phân tích gợi ý |
| --- | --- |
| 1 | Tính bí mật/toàn vẹn và phân quyền cấp đối tượng có thể bị ảnh hưởng. JWT xác minh danh tính/claim theo chính sách, nhưng không tự xác minh user có quyền sửa đối tượng đích. |
| 2 | “Chỉ chủ thể có quyền với người nhận tiền mới cập nhật được bản ghi”; “thay đổi ngoài phạm vi bị từ chối và không ghi dữ liệu”. Test user A sửa recipient B, token thiếu quyền, thay ID, quyền bị thu hồi, đường API khác. |
| 3 | Developer tái hiện/sửa/test; Tech Lead review và chịu trách nhiệm kỹ thuật; Security đánh giá nguy cơ/lỗ hổng; Ops phối hợp deploy/log; chủ sở hữu rủi ro quyết định phần rủi ro cần chấp nhận theo chính sách. |
| 4 | Test thất bại trước sửa, test pass sau sửa, PR/review, commit và CI, artifact digest, bằng chứng deployment, thử nghiệm kiểm chứng ở môi trường đích và thông tin giới hạn. |
| 5 | Người có thẩm quyền theo chính sách phê duyệt; hồ sơ ghi ảnh hưởng, biện pháp tạm thời, người sở hữu, thời hạn, trigger xem xét và kế hoạch sửa/kiểm chứng. Ngoại lệ không biến lỗ hổng thành control đạt. |

**Bài tự thực hành:** chọn một endpoint trong ứng dụng Java mà bạn đang học (đọc dữ liệu, xuất file hoặc cập nhật hồ sơ). Viết một bản ghi gồm `RISK` → `REQ` → `CTRL` → `TEST` → `EV`; đưa ra tối thiểu ba ca bị từ chối, một ca hợp lệ và giải thích **bằng chứng nào vẫn còn thiếu** để kết luận control có hiệu lực trên production.

## Ghi nhớ

- Developer là một vai trò trung tâm của **security assurance**, vì trực tiếp hiện thực và kiểm chứng security controls ở tầng ứng dụng.
- Công việc cần đi theo chuỗi **rủi ro → yêu cầu → control → test → evidence → đánh giá → khắc phục và retest**, với người chịu trách nhiệm rõ ràng.
- **Authentication không thay thế authorization**, test thành công không thay thế xác minh phạm vi, CI xanh không thay thế chứng cứ về môi trường production.
- Bằng chứng tốt cần gắn với **claim, phạm vi, commit/build, thời điểm, phương pháp, kết quả và giới hạn**; finding chỉ đóng khi có kết quả xác minh lại phù hợp.
- Developer phối hợp với Tech Lead, Security, Ops, chủ sở hữu rủi ro và Audit để duy trì một chương trình security assurance **liên tục trong phát triển và vận hành**.

# Di trú identity source trong quản lý vòng đời danh tính (IAM)

> **Chương:** IAM migration  
> **Chủ đề:** Di trú identity source  
> **Phạm vi:** Quản lý vòng đời danh tính trong Identity and Access Management (IAM), từ xác minh danh tính, tạo tài khoản, cấp quyền đến điều chỉnh và thu hồi quyền theo mô hình Joiner–Mover–Leaver (JML).

## 1. Học được gì sau bài này?

Sau bài học, bạn có thể:

1. Phân biệt **identity source** (nguồn dữ liệu danh tính), **identity provider** (IdP), **directory**, hệ thống IAM/IGA và ứng dụng sử dụng danh tính.
2. Xác định nguồn có thẩm quyền cho từng thuộc tính, xây dựng khóa định danh ổn định và lập bản đồ liên kết giữa danh tính cũ và mới.
3. Thiết kế quá trình di trú không tạo tài khoản trùng, không làm mất luồng đăng nhập và không để lại quyền truy cập ngoài ý muốn.
4. Bảo toàn các hành vi Joiner–Mover–Leaver, RBAC/ABAC, SSO, SCIM, rà soát quyền, nhật ký kiểm toán và tài khoản phi con người trong thời gian chuyển đổi.
5. Lập kế hoạch thử nghiệm, pilot, cutover, đối soát, rollback và nghiệm thu dựa trên bằng chứng.

**Câu hỏi xuyên suốt:** Khi công ty đổi hệ thống nhân sự hoặc chuyển nguồn danh tính từ Active Directory sang nền tảng mới, làm thế nào để một người vẫn được nhận diện là *chính người đó*, có đúng tài khoản và quyền, kể cả khi email, mã nhân viên, phòng ban hoặc vị trí thay đổi?

## 2. Identity source là gì và tại sao phải di trú?

### 2.1. Các thành phần dễ nhầm lẫn

Một hệ thống IAM thực tế thường có nhiều nơi chứa thông tin về người dùng:

| Thành phần | Trách nhiệm điển hình | Ví dụ minh họa |
|---|---|---|
| **Identity source** | Nơi phát sinh hoặc xác nhận dữ liệu danh tính có thẩm quyền theo từng phạm vi | HRIS, hệ thống nhà thầu, danh bạ đối tác |
| **Directory** | Lưu trữ và tra cứu tài khoản/nhóm, có thể phục vụ xác thực | Active Directory, LDAP, cloud directory |
| **IdP** | Xác thực người dùng, phát hành phiên hoặc token cho ứng dụng | IdP hỗ trợ OIDC/SAML và MFA |
| **IAM/IGA** | Áp dụng quy tắc cấp quyền, phê duyệt, rà soát, thu hồi và kiểm toán | Bộ máy quản lý vòng đời danh tính |
| **Ứng dụng đích** | Nhận tài khoản, vai trò và thực thi quyền cục bộ | CRM, ERP, Git, hệ thống nội bộ |
| **Provisioning connector** | Đồng bộ tài khoản/quyền từ bộ máy IAM đến hệ đích | SCIM 2.0, API, agent, connector riêng |

**Nguồn danh tính** không đồng nghĩa với nơi người dùng nhập mật khẩu. Ví dụ, HRIS có thẩm quyền về ngày bắt đầu làm việc và bộ phận; IdP quản lý đăng nhập và MFA; ứng dụng CRM quản lý một số quyền chuyên môn. Di trú HRIS là thay nguồn dữ liệu đầu vào; di trú IdP là thay tầng xác thực; hai việc có thể xảy ra cùng dự án nhưng có rủi ro và bước kiểm thử khác nhau.

Một tổ chức có thể có nhiều nguồn hợp lệ: HRIS cho nhân viên, vendor management system cho nhà thầu, hệ thống đối tác cho người dùng B2B. Vì vậy, cần định nghĩa **nguồn có thẩm quyền theo thuộc tính và loại danh tính**, thay vì giả định một hệ thống sở hữu mọi dữ liệu.

### 2.2. Khi nào di trú identity source?

Các tình huống thường gặp:

- Thay HRIS, hợp nhất dữ liệu nhân sự sau sáp nhập hoặc tách công ty.
- Chuyển từ AD/LDAP tại chỗ lên cloud directory hoặc IdP.
- Hợp nhất nhiều tenant/directory, thay cách tạo tài khoản nhân viên, nhà thầu, đối tác.
- Chuẩn hóa luồng provisioning từ tác vụ thủ công sang SCIM/API.
- Chuyển ownership của một nhóm thuộc tính từ hệ thống cũ sang hệ thống mới.

Mục tiêu kinh doanh là bảo đảm danh tính đúng và quyền đúng trong toàn bộ vòng đời. Mục tiêu bảo mật là giảm **orphan account** (tài khoản không còn chủ sở hữu hợp lệ), **stale access** (quyền không còn lý do tồn tại), cấp quyền sai đối tượng và khoảng trống kiểm toán.

### 2.3. Sơ đồ luồng điển hình

~~~mermaid
flowchart LR
    H["HRIS: nhân viên"] --> I["Bộ máy vòng đời IAM/IGA"]
    V["Nguồn nhà thầu, đối tác"] --> I
    I --> D["Directory / IdP"]
    D --> S["SSO: OIDC hoặc SAML"]
    S --> A["Ứng dụng nghiệp vụ"]
    I --> P["SCIM / API provisioning"]
    P --> A
    I --> R["RBAC / ABAC / phê duyệt"]
    R --> P
    I --> L["Audit, đối soát và cảnh báo"]
    A --> L
~~~

Đường **SSO** giải quyết cách đăng nhập; đường **provisioning** giải quyết sự tồn tại tài khoản và các quyền ở ứng dụng. Cho phép đăng nhập qua IdP mới chưa chứng minh rằng ứng dụng đã gỡ quyền cũ hoặc đã liên kết tài khoản đúng người.

## 3. Những bất biến cần giữ trong suốt quá trình di trú

Trước khi chọn công cụ, nhóm triển khai phải thống nhất các điều kiện luôn đúng:

| Bất biến | Ý nghĩa thực tế | Cách xác minh |
|---|---|---|
| **Một chủ thể, một danh tính chuẩn** | Một nhân viên chuyển nguồn vẫn liên kết về cùng một person ID nội bộ | Không có cặp bản ghi hoạt động trùng chủ thể ngoài ngoại lệ đã duyệt |
| **Định danh không đổi theo email** | Đổi email/tên/phòng ban không tạo người mới | Thử ca đổi email và tên đăng nhập |
| **Quyền có lý do hợp lệ** | Mọi quyền đều có chủ sở hữu, nguồn cấp và thời hạn/chính sách thích hợp | So sánh quyền kỳ vọng với quyền thực tế |
| **Leaver bị chặn đúng hạn** | Người rời tổ chức không thể tiếp tục dùng phiên, token hay tài khoản ứng dụng | Kiểm thử vô hiệu hóa tài khoản, session và API token liên quan |
| **Chuyển vai trò xử lý cả cấp và thu hồi** | Mover không giữ vô hạn quyền vị trí cũ | Đối chiếu quyền trước/sau thời điểm hiệu lực |
| **Không mất dấu vết kiểm toán** | Mọi thay đổi có nguyên nhân, người phê duyệt và kết quả | Tra cứu correlation ID xuyên suốt luồng |
| **Có thể dừng và phục hồi có kiểm soát** | Lỗi hàng loạt không biến thành hàng loạt vô hiệu hóa hoặc cấp quyền | Thử chế độ pause, dry-run, rollback trong pilot |

Những bất biến này là tiêu chí nghiệm thu. Các chỉ số như “đã sao chép 100% dòng HRIS” hoặc “100% người dùng đăng nhập được” chỉ phản ánh một phần bài toán.

## 4. Khảo sát hiện trạng và xác định hệ thống có thẩm quyền

### 4.1. Lập inventory

Với mỗi nguồn hoặc ứng dụng, cần có: tên hệ thống, owner vận hành, owner nghiệp vụ, loại danh tính, trường dữ liệu, cơ chế tạo/sửa/xóa, lịch đồng bộ, API/connector, quy tắc khóa, nhóm/quyền được quản lý, SLA vô hiệu hóa, cơ chế audit và phụ thuộc đăng nhập. Phải phân biệt tài khoản người dùng, tài khoản dịch vụ, tài khoản đặc quyền và tài khoản khẩn cấp.

Một dòng inventory tối thiểu có dạng:

| Hệ thống | Đối tượng | Có thẩm quyền về | Cơ chế đồng bộ | Rủi ro chính |
|---|---|---|---|---|
| HRIS-A (cũ) | Nhân viên | Trạng thái lao động, đơn vị, quản lý | Batch hằng ngày | Trễ sự kiện leaver |
| HRIS-B (mới) | Nhân viên | Cùng các trường sau cutover | Event/API | ID mới không trùng ID cũ |
| IdP | Tài khoản đăng nhập | MFA, trạng thái xác thực, danh tính liên kết | API/SSO | Tạo user mới và mất liên kết SSO |
| CRM | Người dùng được cấp quyền | Vai trò CRM có phê duyệt | SCIM + API riêng | Quyền cục bộ tồn dư |
| PAM / Vault | Danh tính đặc quyền | Credential, phiên quản trị, bí mật | API/quy trình riêng | Không thu hồi được quyền nâng cao |

### 4.2. Ma trận ownership theo thuộc tính

Không nhất thiết mọi trường do cùng một nguồn quyết định:

| Thuộc tính | Nguồn có thẩm quyền dự kiến | Lưu ý |
|---|---|---|
| Mã chủ thể chuẩn nội bộ (person key) | Identity registry / IAM | Bất biến, không tái sử dụng |
| Tình trạng làm việc, ngày hiệu lực | HRIS | Xử lý ngày tương lai và sửa hồi tố |
| Department, cost center, manager | HRIS hoặc nguồn được quản trị tương ứng | Cần quy tắc mã phòng ban và cấp trên |
| Username / địa chỉ email | Quy trình directory/email đã quy định | Email có thể đổi và được tái sử dụng |
| MFA, phương thức đăng nhập | IdP | Không lấy trạng thái MFA từ HRIS |
| Nhóm/role mặc định | Chính sách IAM/IGA | Dẫn xuất từ thuộc tính và phê duyệt |
| Role đặc thù trong CRM | Owner ứng dụng hoặc IAM theo hợp đồng rõ ràng | Tránh hai nguồn cùng ghi cùng một role |

Nếu HRIS và ứng dụng đồng thời ghi thuộc tính manager/role mà không có luật ưu tiên, hiện tượng **last-write-wins** có thể âm thầm đảo ngược quyết định cấp quyền. Hãy xác định một writer có thẩm quyền cho mỗi thuộc tính trong từng giai đoạn, cùng cách xử lý ngoại lệ và thời điểm bàn giao ownership.

## 5. Liên kết danh tính cũ và mới: phần khó nhất

### 5.1. Khóa danh tính chuẩn và các ID khác

Trong di trú, rất nhiều giá trị trông giống định danh nhưng không có cùng tính chất:

- **Canonical person ID:** khóa nội bộ ổn định cho một chủ thể, không phụ thuộc email hay hệ nguồn; nên được tạo hoặc duy trì bởi identity registry.
- **Source ID:** khóa của bản ghi tại HRIS-A/HRIS-B; chỉ được coi là ổn định nếu nhà cung cấp cam kết không tái sử dụng.
- **Directory object ID:** khóa đối tượng tài khoản tại directory, có thể thay nếu tài khoản được tạo lại.
- **SCIM id:** định danh tài nguyên do service provider cấp trong phạm vi dịch vụ đó; không tự đồng nhất với ID HRIS.
- **SCIM externalId:** giá trị phía client dùng để liên kết bản ghi từ hệ quản lý danh tính; quy ước cụ thể phải nhất quán và được hệ đích hỗ trợ.
- **OIDC sub:** định danh subject theo issuer; nên ghép cặp **issuer + sub** khi làm khóa nhận diện federated subject.
- **Email/UPN:** thuộc tính liên hệ/đăng nhập có thể đổi, đổi miền hoặc được cấp lại; không dùng làm khóa ghép tự động duy nhất.

Ví dụ: người có canonical ID **person-00421** được HRIS-A gọi là **E01877**, HRIS-B gọi là **W93211**; IdP giữ một subject riêng; CRM có SCIM id riêng. Mọi liên kết phải quy về **person-00421**, không tạo ra hai nhân viên chỉ vì hai mã nguồn khác nhau.

Một bản đồ liên kết minh họa:

~~~yaml
canonicalPersonId: person-00421
type: employee
sourceLinks:
  - system: hris-a
    sourceId: E01877
  - system: hris-b
    sourceId: W93211
accounts:
  - system: idp
    accountId: idp-object-7281
  - system: crm
    scimId: crm-user-913
lifecycleStatus: active
~~~

Đây là **mô hình dữ liệu minh họa**, không phải schema tiêu chuẩn áp dụng nguyên xi cho mọi IdP.

### 5.2. Nguyên tắc matching an toàn

Thực hiện so khớp theo thứ tự có kiểm soát:

1. **Liên kết đáng tin cậy:** có bảng mapping đã xác minh giữa source ID cũ, source ID mới và canonical ID.
2. **Đối chiếu bằng chứng:** trong trường hợp thiếu mapping, đối chiếu nhiều thuộc tính độc lập và dữ liệu từ bộ phận có trách nhiệm; tránh chỉ dùng tên hoặc email.
3. **Phân loại mơ hồ:** hai bản ghi có khả năng cùng người hoặc một bản ghi khớp nhiều người phải đưa vào hàng đợi xác minh thủ công.
4. **Chốt mapping có audit:** ghi người phê duyệt, thời điểm, nguồn đối chiếu, phiên bản mapping, lý do merge/link.
5. **Áp ràng buộc duy nhất:** khóa cặp (system, sourceId) chỉ trỏ về một canonical ID tại một thời điểm; chặn tự động gộp qua tenant/đơn vị khi chưa xác thực.

Đừng tự động hợp nhất tài khoản chỉ vì có cùng email. Một email có thể được tái sử dụng; nhà thầu có thể trở thành nhân viên; hai công ty sáp nhập có thể có username giống nhau.

### 5.3. Phân biệt *link* và *merge*

**Link** thêm quan hệ giữa danh tính chuẩn và bản ghi nguồn/tài khoản đích đã xác minh. **Merge** hợp nhất hai hồ sơ vốn được hệ thống coi là hai chủ thể; đây là thao tác có thể ảnh hưởng lịch sử phê duyệt và quyền, cần quy trình riêng cùng khả năng truy vết. Trong pilot, ưu tiên link khi có bằng chứng; các trường hợp merge mơ hồ phải được cô lập để xử lý.

**Không xóa danh tính cũ ngay sau khi link.** Cần giữ mapping và các khóa tham chiếu đủ lâu cho audit, đối soát và rollback theo chính sách lưu giữ dữ liệu.

## 6. Bảo toàn Joiner–Mover–Leaver khi đổi nguồn

Một cuộc di trú thành công phải chuyển **logic nghiệp vụ** chứ không chỉ dữ liệu.

| Giai đoạn | Sự kiện đầu vào | Hành động IAM kỳ vọng | Kiểm thử quan trọng |
|---|---|---|---|
| **Joiner** | Hợp đồng hợp lệ, ngày bắt đầu, đơn vị, quản lý | Xác minh nguồn; tạo/liên kết danh tính; tạo account; cấp quyền tối thiểu theo role, yêu cầu MFA | Không cấp sớm trái chính sách; không tạo account kép |
| **Mover** | Đổi phòng ban, vị trí, quản lý, loại hợp đồng | Tính lại RBAC/ABAC; cấp quyền mới sau phê duyệt; thu hồi quyền cũ và token/phiên khi cần | Không tích lũy role cũ; thực thi đúng effective time |
| **Leaver** | Chấm dứt hợp đồng, nghỉ việc, hết hạn nhà thầu | Ngừng đăng nhập; thu hồi quyền ứng dụng, token, khóa/phiên; xử lý sở hữu tài nguyên | Quyền trực tiếp và ngoại lệ đều được rà soát |
| **Rejoiner** | Người cũ quay lại sau khoảng nghỉ | Xác minh danh tính lại; quyết định khôi phục/liên kết theo chính sách | Không phục hồi quyền cũ ngoài ý muốn |
| **Leave of absence** | Tạm nghỉ, tạm khóa vì lý do hợp lệ | Áp chính sách trạng thái tạm thời, thời hạn và phục hồi | Không mặc định coi là leaver vĩnh viễn |

### 6.1. Joiner: tạo đúng một bản ghi

Với nhân viên được tuyển nhưng chưa đến ngày bắt đầu, nguồn mới có thể phát sự kiện trước vài ngày. Bộ máy IAM cần tách **đã có hồ sơ** với **được phép hoạt động**: có thể chuẩn bị tài khoản nhưng việc bật đăng nhập, cấp quyền nhạy cảm phải tuân theo thời điểm hiệu lực. Người dùng đã có ở IdP/ứng dụng phải được liên kết thay vì tạo bản ghi thứ hai.

### 6.2. Mover: cấp mới đi kèm thu hồi cũ

Ví dụ một nhân viên chuyển từ phòng Kế toán sang Mua hàng:

- Quyền xem sổ cái chỉ được giữ nếu vẫn có lý do nghiệp vụ đã được phê duyệt.
- Role Mua hàng được cấp theo tiêu chí mới và kiểm soát phân tách nhiệm vụ (SoD).
- Các nhóm tĩnh, quyền trực tiếp tại ứng dụng, quyền nâng cao trong PAM và phiên hiện tại đều phải được đánh giá, không chỉ nhóm mặc định từ directory.
- Cần chính sách rõ cho giai đoạn chuyển giao, có thời hạn, người chấp thuận và tự hết hạn. Không để ngoại lệ chuyển giao tồn tại mãi.

### 6.3. Leaver: khóa đăng nhập chưa đủ

Một người đã bị disable trong IdP vẫn có thể tồn tại: phiên đang mở, refresh token, API key, SSH key, quyền trong ứng dụng không dùng SSO, tài khoản local hoặc credential của bên thứ ba. Quy trình leaver phải biết cách thu hồi các đường truy cập này hoặc chuyển thành ticket kiểm soát có owner và hạn xử lý.

**Tuyệt đối không coi việc một người biến mất khỏi một đợt export HRIS là bằng chứng leaver duy nhất.** Một file rỗng do lỗi kết nối có thể gây mass deprovision. Muốn vô hiệu hóa hàng loạt cần trạng thái đầu vào đáng tin, kiểm soát số lượng bất thường và xác thực từ nguồn có thẩm quyền.

### 6.4. Tài khoản phi con người và ngoại lệ

Service account, workload identity, bot, tài khoản tích hợp và tài khoản khẩn cấp thường không xuất phát từ HRIS. Hãy quản lý chúng trong registry riêng có owner chịu trách nhiệm, phạm vi quyền, thời hạn/chu kỳ review, quy trình quay vòng credential và kế hoạch bàn giao owner khi nhân viên rời công ty. Không dùng sự kiện leaver của cá nhân để tự động xóa tài khoản dịch vụ mà không đánh giá phụ thuộc; đồng thời không để tài khoản dịch vụ vô chủ.

## 7. Các chiến lược di trú và cách chọn

| Chiến lược | Cơ chế | Phù hợp khi | Rủi ro / biện pháp |
|---|---|---|---|
| **Big-bang cutover** | Chuyển mọi identity trong một cửa sổ | Quy mô nhỏ, phụ thuộc ít, rollback đã thử | Tác động lớn nếu mapping sai; yêu cầu kế hoạch dừng/khôi phục |
| **Phased migration** | Chuyển từng nhóm tổ chức/tenant/ứng dụng | Hệ thống lớn, nhiều đơn vị | Cần ngăn trùng quyền và xác định ownership rõ cho từng nhóm |
| **Shadow mode** | Nguồn mới chạy đọc/so sánh, chưa ghi quyền chính thức | Muốn phát hiện sai biệt trước cutover | Không được để shadow ghi nhầm ứng dụng |
| **Coexistence có ràng buộc** | Nguồn cũ và mới tồn tại song song trong thời gian ngắn | Phụ thuộc chưa thể chuyển cùng lúc | Chỉ một writer cho từng trường/đối tượng; có thứ tự ưu tiên rõ |
| **Federation bridge** | Giữ xác thực qua IdP cũ một thời gian trong khi đổi nguồn/IdP | Nhiều ứng dụng legacy | Cần quản lý trust, session, claim và ngày kết thúc bridge |

**Gợi ý chọn chiến lược:** Với một tổ chức có hàng chục ứng dụng và dữ liệu nguồn thiếu đồng nhất, shadow mode rồi phased migration thường giúp giảm rủi ro hơn chuyển đồng loạt. Big-bang vẫn khả thi nếu có inventory chính xác, liên kết danh tính đã được phê duyệt, quy trình dự phòng và rehearsal thực tế.

Một bất biến cần áp dụng trong mọi chiến lược là: **tại bất kỳ thời điểm nào, phải biết hệ thống nào được phép ghi mỗi thuộc tính hoặc quyết định cấp quyền.** Dual-read giúp đối chiếu; dual-write thiếu điều phối dễ gây vòng lặp, tranh chấp phiên bản và cấp quyền lại sau khi đã thu hồi.

## 8. Quy trình di trú theo từng giai đoạn

### Giai đoạn 0 — Xác định phạm vi, rủi ro và chuẩn nghiệm thu

Xác định nhóm người dùng, ứng dụng đích, tenant, luồng SSO, nhóm đặc quyền, hệ thống quan trọng, yêu cầu lưu giữ dữ liệu, cửa sổ cutover, vai trò quyết định go/no-go và quyền dừng. Chốt RACI giữa HR, IT/IAM, security, owner ứng dụng và vận hành. Thiết lập tiêu chí nghiệm thu trước khi thay đổi.

Ví dụ tiêu chí cho một pilot: 100% người trong pilot có mapping được xác minh; không có tài khoản đặc quyền mới thiếu phê duyệt; không có tài khoản trùng chưa được xử lý; các tình huống JML và rollback bắt buộc đều pass. Ngưỡng cụ thể phải theo mức rủi ro tổ chức, không mặc định số của ví dụ là tiêu chuẩn chung.

### Giai đoạn 1 — Chuẩn hóa dữ liệu và chuẩn bị mapping

- Xuất snapshot có thời điểm, số bản ghi, checksum và nguồn gốc; hạn chế quyền truy cập dữ liệu nhạy cảm.
- Làm sạch giá trị phòng ban, manager, loại nhân sự, trạng thái, timezone, ngày hiệu lực, định danh có thể trùng.
- Xây bảng đối chiếu **old source ID → canonical ID → new source ID**, lưu trạng thái matching và bằng chứng.
- Đánh dấu bản ghi mơ hồ, người đã rời tổ chức, account orphan, service account và quyền ngoại lệ.
- Đảm bảo mapping có phiên bản, ràng buộc duy nhất và không bị tự viết lại khi sự kiện phát lại.

### Giai đoạn 2 — Chuẩn bị connector và chính sách

Thiết lập SCIM/API, phân tách môi trường test/prod, secret ở vault, quyền connector tối thiểu, giới hạn tốc độ, retry có backoff, dead-letter queue, giám sát và rollback. Chuyển luật role/grant/revoke sang cơ chế quản trị mới, kiểm tra SoD và quy trình phê duyệt. Nếu đổi IdP, kiểm tra issuer, audience, chữ ký, claim mapping, MFA, provisioning và tài khoản ứng dụng dựa trên SSO.

### Giai đoạn 3 — Shadow + dry-run + reconciliation

Chạy nguồn mới ở **chế độ chỉ đọc/giả lập tác động**: với mỗi identity tính danh tính/nhóm/quyền kỳ vọng và so sánh với hiện trạng; không thực thi thay đổi thật. Phân loại chênh lệch: do chuẩn hóa dữ liệu, do chính sách, do quyền cấp trực tiếp, do hệ thống đích hay do lỗi mapping. Xử lý các ca mơ hồ trước pilot.

### Giai đoạn 4 — Pilot và rehearsal

Chọn nhóm pilot có đủ nhân viên mới, chuyển role, leaver, nhà thầu, account đặc quyền và ứng dụng có cơ chế provisioning khác nhau. Thử không chỉ đường đi bình thường mà cả lỗi API, event trùng/lệch thứ tự, gián đoạn HRIS, rollback và session còn tồn tại. Ghi lại thời gian phát hiện, thời gian thu hồi, kết quả đối soát và các thao tác thủ công.

### Giai đoạn 5 — Cutover có kiểm soát

1. Chốt mapping và danh sách ngoại lệ tại thời điểm cutover; lưu snapshot và điểm phục hồi.
2. Tạm dừng hoặc đóng băng các ghi có xung đột theo runbook; xác nhận nguồn đang sở hữu từng trường.
3. Đồng bộ delta cuối cùng từ nguồn cũ; kiểm tra thứ tự phiên bản và số bản ghi.
4. Chuyển writer có thẩm quyền sang nguồn mới theo cohort/thuộc tính đã công bố.
5. Bật provisioning theo từng đợt có giới hạn; theo dõi bất thường và chặn mass update.
6. Chạy reconciliation và các ca đăng nhập/JML thực tế; quyết định tiếp tục, pause hay rollback.
7. Ghi nhận người phê duyệt, timestamp, ticket và bằng chứng cho mỗi quyết định go/no-go.

### Giai đoạn 6 — Hypercare và loại bỏ phụ thuộc cũ

Trong giai đoạn giám sát tăng cường, rà soát login failures, duplicate account, tình trạng SCIM, leaver latency, quyền tồn dư, event bị bỏ sót và queue lỗi. Chỉ decommission nguồn cũ, connector cũ, federation bridge và credential cũ khi có bằng chứng các ứng dụng đã chuyển xong, dữ liệu audit đã được bảo quản và rollback không còn phụ thuộc vào chúng. Việc xóa thông tin lịch sử phải theo chính sách lưu giữ và yêu cầu pháp lý áp dụng.

~~~mermaid
flowchart TD
    A["Inventory và xác định authority"] --> B["Chuẩn hóa dữ liệu + mapping"]
    B --> C["Shadow và đối soát"]
    C --> D{"Mapping và JML đạt yêu cầu?"}
    D -- "Chưa" --> B
    D -- "Đạt" --> E["Pilot và rehearsal"]
    E --> F{"Go / No-go"}
    F -- "No-go" --> C
    F -- "Go" --> G["Cutover theo cohort"]
    G --> H["Reconcile và giám sát"]
    H --> I{"Sai lệch nghiêm trọng?"}
    I -- "Có" --> J["Pause / rollback có kiểm soát"]
    J --> C
    I -- "Không" --> K["Hypercare, decommission có phê duyệt"]
~~~

## 9. Đồng bộ kỹ thuật: tính nhất quán quan trọng hơn tốc độ

### 9.1. Event, snapshot và thứ tự cập nhật

Hệ mới có thể phát nhiều sự kiện cho cùng một người, không bảo đảm đến đúng thứ tự. Phải thiết kế consumer **idempotent** và xử lý phiên bản: cùng một sự kiện được nhận lại không tạo tài khoản/quyền mới; sự kiện cũ hơn không được phục hồi thuộc tính hoặc quyền đã bị thay bởi trạng thái mới.

Ví dụ thông điệp chuẩn hóa (minh họa):

~~~json
{
  "eventId": "evt-2026-000918",
  "source": "hris-b",
  "sourcePersonId": "W93211",
  "canonicalPersonId": "person-00421",
  "sourceVersion": 42,
  "eventType": "employment.updated",
  "effectiveAt": "2026-12-01T00:00:00Z",
  "data": {
    "status": "active",
    "department": "procurement",
    "managerCanonicalId": "person-00215"
  }
}
~~~

Luồng xử lý đề xuất:

~~~text
Nhận sự kiện
  -> Xác thực nguồn gửi và schema
  -> Kiểm tra eventId / sourceVersion / thời điểm hiệu lực
  -> Tra mapping đã được xác minh
  -> Nếu mơ hồ: quarantine + alert, không tự cấp quyền
  -> Chuẩn hóa identity và áp chính sách JML
  -> Tính desired state của từng ứng dụng
  -> Gọi connector bằng thao tác idempotent
  -> Ghi audit và actual state
  -> Reconcile, retry có backoff hoặc mở ticket nếu thất bại
~~~

**Idempotent** không có nghĩa là mọi API đích đều hỗ trợ idempotency key; khi không hỗ trợ, connector cần kiểm tra trạng thái thực tế và dùng khóa liên kết ổn định trước khi tạo tài khoản. Retry phải phân biệt lỗi tạm thời, xung đột, không tìm thấy và lỗi chính sách.

### 9.2. SCIM: provisioning tài khoản khác với SSO

SCIM 2.0 cung cấp mô hình tài nguyên và giao thức quản lý user/group thường dùng trong provisioning. Khi tạo user tại một ứng dụng hỗ trợ SCIM, IAM có thể gửi dữ liệu kiểu:

~~~json
{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
  "externalId": "person-00421",
  "userName": "minh.nguyen@example.test",
  "name": {
    "givenName": "Minh",
    "familyName": "Nguyen"
  },
  "active": true
}
~~~

Khi leaver, hệ đích có thể nhận yêu cầu cập nhật trạng thái:

~~~http
PATCH /scim/v2/Users/crm-user-913
Content-Type: application/scim+json
Authorization: Bearer <token>
~~~

~~~json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "Replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

**Lưu ý:** payload trên là ví dụ theo cấu trúc SCIM 2.0; URL, các trường bắt buộc, phản hồi và hiệu lực thu hồi phiên/token tùy nhà cung cấp. Không dùng giá trị token mẫu trong hệ thống thật. Vô hiệu hóa SCIM user không mặc nhiên hủy mọi phiên hay API key trong ứng dụng; cần kiểm tra contract và cơ chế revoke tương ứng.

Khi migrate SCIM, phải xác minh tính duy nhất/semantics của **externalId**, ánh xạ group và độ tương thích connector. Không được giả định hai ứng dụng diễn giải mọi trường SCIM giống nhau.

### 9.3. SSO và khóa liên kết khi đổi IdP

Với OIDC, một ứng dụng thường liên kết tài khoản theo subject trong ngữ cảnh issuer. Nếu IdP thay đổi, claim **sub** có thể khác; với SAML, NameID và cách định danh ở SP cũng có thể đổi. Nếu ứng dụng chỉ dựa vào email để tự nối tài khoản, có nguy cơ chiếm nhầm tài khoản hoặc tạo tài khoản kép.

Trước cutover đăng nhập, cần xác định cho từng ứng dụng:

- Khóa liên kết SSO hiện tại, issuer/audience và claim bắt buộc.
- Khả năng **pre-link** tài khoản cũ với subject mới, dựa trên mapping đã xác minh.
- Chính sách MFA, phishing-resistant authentication, đăng ký thiết bị và khôi phục tài khoản.
- Cách chuyển group/role claim, chứng chỉ ký, metadata federation và giờ hết hạn phiên.
- Cơ chế vô hiệu hóa hoặc thu hồi phiên cũ sau khi thay trust.

Không lẫn lộn việc đổi secret/chứng chỉ với đổi danh tính: rotate signing certificate có thể giữ nguyên subject; đổi issuer/sub có thể đòi hỏi migration account-linking thật sự.

### 9.4. RBAC, ABAC và quyền cấp trực tiếp

RBAC gắn quyền với role; ABAC sử dụng thuộc tính như department, location, employmentType và độ nhạy tài nguyên để quyết định quyền. Trong di trú:

1. Chuẩn hóa giá trị thuộc tính; ví dụ mã đơn vị **FIN-01** ở nguồn cũ chuyển thành **finance** ở nguồn mới.
2. So sánh role/attribute policy trước và sau cutover trên cùng tập identity mẫu.
3. Rà soát quyền **direct grant**, exception, delegated admin, nhóm lồng nhau, policy ứng dụng cục bộ và quyền đặc quyền.
4. Đảm bảo quyền role cũ được thu hồi khi role mới có hiệu lực; nếu có overlap, xác định thời hạn và approver.
5. Thiết lập SoD cho những tổ hợp nguy hiểm (ví dụ người tạo nhà cung cấp đồng thời duyệt thanh toán).

Chỉ đồng bộ các nhóm từ IdP sang ứng dụng sẽ không phát hiện đầy đủ quyền được cấp trực tiếp trong ứng dụng hoặc PAM.

## 10. Đối soát quyền và chống drift

### 10.1. Desired state và actual state

**Desired state** là danh tính, tài khoản và quyền lẽ ra phải có theo nguồn có thẩm quyền, chính sách IAM và ngoại lệ đã phê duyệt. **Actual state** là trạng thái thật thu được từ IdP, directory và từng ứng dụng. Reconciliation là so sánh hai phía, xác định nguyên nhân rồi áp sửa chữa có kiểm soát.

| Chênh lệch | Khả năng nguyên nhân | Xử lý đề xuất |
|---|---|---|
| Có trong nguồn, chưa có account đích | Provisioning thất bại hoặc chưa đến hiệu lực | Retry/ticket theo SLA, không tự tạo trùng |
| Không còn quyền kỳ vọng nhưng app vẫn cấp | Direct grant, connector lỗi, sai rule | Thu hồi theo policy, ưu tiên quyền nhạy cảm |
| App có account không map được vào người | Orphan, service account bị phân loại sai | Cách ly/điều tra owner trước khi xóa |
| Hai app account cùng trỏ một người | Đã tạo trùng trong di trú | Khóa cấp thêm, xử lý liên kết/merge có phê duyệt |
| Một app account trỏ hai chủ thể | Mâu thuẫn mapping nghiêm trọng | Dừng tự động hóa đối tượng, điều tra và khắc phục |
| Role thay đổi qua lại liên tục | Hai writer tranh chấp hoặc event sai thứ tự | Pause connector, sửa ownership/version |
| Số leaver tăng bất thường | Thiếu batch, lỗi nguồn hoặc sự kiện hàng loạt thật | Guardrail chặn mass disable, xác minh với HR |

### 10.2. Guardrail cho thay đổi hàng loạt

Nên có cảnh báo và cơ chế phê duyệt riêng khi: số lượng deactivate vượt mức vận hành thông thường, một department đột ngột mất toàn bộ nhân sự, quá nhiều người không map được, số bản ghi nguồn giảm mạnh, hoặc số direct grant tăng bất thường. Trạng thái **nguồn không khả dụng/không đầy đủ** phải được xử lý khác với **nguồn xác nhận người dùng nghỉ việc**.

Ví dụ guardrail mang tính minh họa: nếu một đợt đồng bộ làm 25% nhân viên active bị đánh dấu leaver, hệ thống đưa lệnh vào trạng thái chờ xác minh thay vì chạy ngay. Ngưỡng thực tế phải dựa trên baseline và kế hoạch di trú đã phê duyệt.

### 10.3. Đo chất lượng

Các chỉ số hữu ích:

- **Mapping coverage:** số identity có mapping đã xác minh / tổng identity trong phạm vi.
- **Duplicate rate:** số chủ thể có nhiều account ngoài dự kiến / tổng chủ thể.
- **Orphan account rate:** số account không có chủ thể/owner hợp lệ / tổng account, tách riêng service account.
- **Provisioning success rate:** số thao tác tạo/sửa/thu hồi đạt trạng thái kỳ vọng / tổng thao tác hợp lệ.
- **Leaver revocation latency:** thời gian từ mốc hiệu lực leaver đến khi mọi đường truy cập nằm trong phạm vi đã bị thu hồi; báo cáo percentile và các vi phạm SLA.
- **Entitlement drift:** số hoặc tỷ lệ quyền thực tế khác quyền được phê duyệt.
- **Reconciliation lag:** độ trễ giữa thay đổi nguồn và phát hiện/xử lý chênh lệch ở đích.
- **SSO failure rate:** lỗi đăng nhập sau cutover, phân nhóm theo ứng dụng, cohort và nguyên nhân.

Không dùng duy nhất tỉ lệ đăng nhập thành công để đánh giá di trú identity source: người đăng nhập được vẫn có thể đang mang quyền sai.

## 11. Bảo mật, quyền riêng tư và kiểm toán

### 11.1. Giảm quyền trong suốt migration

- Connector chỉ có phạm vi API tối thiểu; tách credentials của read-only shadow và production writer.
- Secret, signing key và API token lưu trong secret manager/vault; rotate credential sau cutover theo runbook.
- Tài khoản break-glass có kiểm soát, giám sát, chứng thực riêng và thử nghiệm định kỳ; không để một lỗi federation khóa toàn bộ quyền quản trị.
- Thực hiện access review cho vai trò đặc quyền, service account owner, exception và quyền trực tiếp trước/sau chuyển đổi.
- Không dùng quyền rộng tạm thời trong migration mà quên ngày hết hạn; mọi exception cần owner và expiry.

### 11.2. Audit trail đủ để điều tra

Mỗi quyết định tạo/link/disable user hoặc grant/revoke role cần truy được:

| Trường audit | Ý nghĩa |
|---|---|
| correlationId / eventId | Ghép sự kiện nguồn, xử lý IAM và tác động ứng dụng |
| canonicalPersonId và sourceLink | Xác định chính xác chủ thể và bản ghi gốc |
| before / after / desired state | Nêu rõ trạng thái đã thay đổi |
| ruleVersion / policyId | Giải thích vì sao quyền được cấp/thu hồi |
| actor / approver | Hệ thống hoặc người ra quyết định và người duyệt |
| timestamp, outcome, targetSystem | Thời điểm hiệu lực và kết quả từng đích |
| exception / ticket / retry | Vì sao thất bại, đã sửa thế nào |

Không ghi password, raw access token, dữ liệu HR nhạy cảm không cần thiết vào log. Mã hóa dữ liệu trong quá trình truyền và lưu trữ, phân quyền truy cập mapping/audit, giới hạn retention phù hợp yêu cầu tổ chức và pháp luật áp dụng.

### 11.3. Hành vi khi có sự cố

Cần runbook riêng cho mapping sai, mass deprovision, mis-provisioning và thất bại SSO. Khi phát hiện sai lệch nghiêm trọng, ưu tiên **dừng writer gây lỗi, cách ly sự kiện và xác minh trạng thái người dùng/quyền**. Rollback không được khôi phục mù trạng thái có đặc quyền trước đây nếu từ đó đến nay người dùng đã nghỉ việc hoặc đã bị thu hồi quyền vì lý do bảo mật.

## 12. Rollback và phục hồi đúng cách

Rollback identity source là hoàn nguyên **quyền phát sinh dữ liệu và trạng thái đồng bộ**, không đơn thuần đổi lại URL API:

1. **Điều kiện kích hoạt:** xác định trước các ngưỡng như liên kết sai người, mất SSO diện rộng, grant nhầm quyền đặc quyền, queue lỗi vượt khả năng xử lý.
2. **Pause writer và giữ bằng chứng:** dừng đúng luồng có vấn đề; giữ event log, snapshot, phiên bản mapping và audit.
3. **Đối chiếu delta từ sau cutover:** nhận diện joiner/mover/leaver phát sinh trong thời gian migration; không bỏ qua thay đổi thật.
4. **Chọn điểm phục hồi:** xác định hệ thống có thẩm quyền và rule version cần khôi phục; bảo đảm không tái cấp quyền đã bị thu hồi hợp lệ.
5. **Replay có kiểm soát:** dùng eventId/version để tránh nhân đôi; thực hiện theo cohort và xác nhận trạng thái thực tế.
6. **Kiểm thử SSO, JML và quyền:** đặc biệt leaver, ứng dụng không dùng SSO và account đặc quyền.
7. **Quyết định tiếp tục:** cập nhật incident, nguyên nhân, hành động phòng ngừa rồi mới thử cutover lại.

Một số thay đổi không thể tự đảo ngược hoàn toàn, như xóa user ở nhà cung cấp, thu hồi credential hoặc chuyển ownership dữ liệu. Vì thế cần kiểm tra khả năng backup/restore thật và hạn chế thao tác phá hủy trong các đợt đầu.

## 13. Tình huống thực tế: thay HRIS-A bằng HRIS-B

Giả sử một công ty có 1.000 nhân viên, dùng HRIS-A để phát sự kiện nhân sự, một IdP để đăng nhập SSO và năm ứng dụng nhận account qua SCIM hoặc API riêng. Công ty thay HRIS-A bằng HRIS-B, trong đó mã nhân viên mới khác hoàn toàn.

### Bước 1: Khớp danh tính

Qua mapping có chứng cứ và rà soát với HR:

- 989 người được liên kết rõ ràng với canonical person ID đang có.
- 8 trường hợp cần xác minh thủ công vì trùng tên hoặc email thay đổi.
- 3 trường hợp chưa có đủ bằng chứng được cách ly, không tự tạo account mới.

Sau khi xử lý ngoại lệ, bộ máy IAM chỉ đổi nguồn có thẩm quyền cho các thuộc tính HR, vẫn giữ canonical ID và liên kết tài khoản đã có.

### Bước 2: Chạy ba ca JML

**Joiner:** Nhân viên Lan có ngày bắt đầu vào tháng tới. HRIS-B phát sự kiện trước ngày hiệu lực. IAM liên kết hồ sơ, chuẩn bị tài khoản theo chính sách nhưng chỉ kích hoạt quyền đúng thời điểm.

**Mover:** Nhân viên Minh chuyển từ Finance sang Procurement. IAM tính lại role, yêu cầu phê duyệt role Procurement, thu hồi quyền sổ cái không còn hợp lệ, cập nhật nhóm/SCIM và xác minh không còn direct grant ở ứng dụng quan trọng.

**Leaver:** Nhà thầu An có ngày hết hạn hợp đồng. Bộ máy IAM nhận nguồn nhà thầu có thẩm quyền (không trông đợi HRIS-B chứa mọi nhà thầu), ngừng SSO, thu hồi tài khoản ứng dụng/API key được gắn với An và chuyển ownership một bot do An quản lý cho người tiếp nhận.

### Bước 3: Đối soát và nghiệm thu

Đợt đầu phát hiện một ứng dụng không thu hồi direct role khi SCIM group bị xóa. Nhóm ứng dụng bổ sung API thu hồi quyền cục bộ và chạy reconciliation lại. Chỉ khi các ca đăng nhập, Joiner, Mover, Leaver, mapping và quyền thực tế đều đạt tiêu chí, nhóm mới mở rộng cohort tiếp theo.

**Bài học rút ra:** Sao chép đủ 1.000 hồ sơ từ HRIS-A sang HRIS-B không đồng nghĩa đã di trú xong; công việc khó là duy trì **identity continuity** và **access correctness** trên các hệ đích.

## 14. Bộ kiểm thử và checklist nghiệm thu

### 14.1. Các ca kiểm thử bắt buộc

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| T01 | User đổi email, giữ person ID | Liên kết account cũ, không tạo mới |
| T02 | Hai user có tên gần giống hoặc email tái sử dụng | Không tự merge; đưa vào xác minh |
| T03 | Joiner có ngày hiệu lực tương lai | Đúng thời điểm mở quyền theo policy |
| T04 | Mover đổi department và manager | Cấp role mới, thu hồi role cũ, kiểm tra SoD |
| T05 | Leaver ở nguồn HR hợp lệ | Chặn SSO, revoke account/quyền/token liên quan trong SLA |
| T06 | Một batch nguồn trống do lỗi mạng | Không mass disable; cảnh báo dữ liệu thiếu |
| T07 | Event lặp hoặc đến sai thứ tự | Kết quả idempotent, không hồi sinh quyền cũ |
| T08 | SCIM/API đích trả lỗi tạm thời | Retry/backoff, audit và đối soát sau xử lý |
| T09 | User có direct grant/PAM privilege | Reconciliation phát hiện quyền tồn dư |
| T10 | Thay IdP làm đổi issuer/sub | Pre-link chính xác; không lẫn account và không mất MFA policy |
| T11 | Service account có owner là leaver | Có xử lý bàn giao owner/secret; không tạo orphan |
| T12 | Rollback sau một số thay đổi JML mới | Không nhân đôi account và không phục hồi quyền bị thu hồi hợp lệ |

### 14.2. Checklist trước khi go-live

- [ ] Có inventory hệ nguồn, IdP, directory, ứng dụng, connector, owner, nhóm đặc quyền và tài khoản phi con người.
- [ ] Có ma trận authority cho từng thuộc tính và người chịu trách nhiệm quyết định xung đột.
- [ ] Canonical ID và bản đồ old/new source ID được xác minh; trường hợp mơ hồ đã được xử lý hoặc cách ly.
- [ ] Có test đối với JML, rejoiner, đổi email, direct grant, session/token và IdP federation.
- [ ] Có kế hoạch SCIM/API idempotency, retry, rate limit, queue lỗi và reconciliation.
- [ ] Có guardrail cho nguồn rỗng, giảm dữ liệu bất thường và mass grant/revoke.
- [ ] Có kế hoạch cutover, trách nhiệm go/no-go, điểm snapshot và rehearsal rollback.
- [ ] Có audit trail, số đo baseline, cảnh báo và cơ chế tiếp nhận incident.
- [ ] Có tiêu chí xác nhận role, quyền và account đúng trên ứng dụng đích.
- [ ] Có kế hoạch loại bỏ connector/credential/trust cũ và giữ hồ sơ theo retention policy.

## 15. Những sai lầm thường gặp

**Dùng email làm khóa chính:** làm mất identity continuity khi email đổi hoặc được tái sử dụng. Giải pháp là canonical ID và mapping có chứng cứ.

**Đồng bộ user mà quên entitlement:** ứng dụng có user đúng nhưng role trực tiếp sai. Giải pháp là đối soát desired/actual state, gồm app local permissions và PAM.

**Cho nguồn cũ và mới cùng ghi:** thuộc tính/role liên tục đảo trạng thái. Giải pháp là single-writer rõ ràng theo thuộc tính và thời điểm.

**Đánh đồng account deactivation với thu hồi truy cập:** SSO bị chặn nhưng token hoặc tài khoản không tích hợp vẫn dùng được. Giải pháp là kiểm thử đa đường truy cập và SLA thu hồi.

**Tự deactivate khi thiếu record:** mất batch dữ liệu bị hiểu là nhân viên nghỉ việc. Giải pháp là phân biệt “source unavailable” với “confirmed leaver” và có mass-change guardrail.

**Chuyển toàn bộ cùng lúc khi chưa giải quyết matching:** lỗi liên kết lan rộng và rollback khó. Giải pháp là shadow, pilot, phased migration và quarantine.

**Quên máy và tài khoản dịch vụ:** owner nghỉ việc khiến service account vô chủ hoặc tích hợp bị ngắt. Giải pháp là non-human identity inventory, quản lý owner và secret lifecycle riêng.

**Chỉ thử đường đi thành công:** không phát hiện lỗi event trùng, race condition, offline API hoặc SSO issuer mismatch. Giải pháp là test những failure mode thực tế trước cutover.

## 16. Câu hỏi tự kiểm tra

1. Nếu HRIS mới sử dụng mã nhân viên khác và email đã thay đổi, bạn cần những bằng chứng nào để liên kết hai bản ghi?
2. Tại sao người dùng đăng nhập SSO thành công vẫn có thể bị coi là chưa di trú hoàn tất?
3. Trong trường hợp một export HRIS trống bất thường, hệ thống nên xử lý thế nào để tránh vô hiệu hóa hàng loạt?
4. Khi nhân viên đổi bộ phận, tại sao cập nhật nhóm mới là chưa đủ?
5. Sự khác biệt giữa SCIM **id**, SCIM **externalId** và cặp OIDC **issuer + sub** ảnh hưởng thế nào đến account linking?
6. Nếu rollback diễn ra sau một sự kiện leaver hợp lệ, làm sao tránh phục hồi lại quyền của người đã rời công ty?
7. Các tài khoản dịch vụ cần được quản lý khác tài khoản nhân viên ở điểm nào?

**Gợi ý trả lời:** Tập trung vào bằng chứng mapping và canonical ID; tách authentication khỏi provisioning; kiểm soát độ tin cậy của nguồn; rà soát quyền cũ và trực tiếp; giữ khóa trong đúng phạm vi; replay trạng thái hiện hành theo version và policy; quản trị owner/secret/service lifecycle độc lập.

## 17. Thuật ngữ và tài liệu nền tảng

| Thuật ngữ | Ý nghĩa |
|---|---|
| **IAM** | Quản lý định danh và quyền truy cập |
| **IGA** | Quản trị danh tính, vai trò, phê duyệt và access review |
| **IdP** | Nhà cung cấp danh tính hỗ trợ xác thực/federation |
| **JML** | Joiner–Mover–Leaver: vào, đổi vai trò và rời tổ chức |
| **HRIS** | Hệ thống thông tin nhân sự |
| **SSO** | Đăng nhập một lần trên nhiều ứng dụng |
| **SCIM** | Chuẩn API quản lý user/group giữa hệ thống |
| **RBAC / ABAC** | Kiểm soát truy cập theo vai trò / thuộc tính |
| **SoD** | Separation of Duties: phân tách nhiệm vụ xung đột |
| **Reconciliation** | So sánh trạng thái kỳ vọng và trạng thái thật |
| **Shadow mode** | Chạy đồng thời để đối chiếu, chưa tác động production |
| **Cutover** | Thời điểm chuyển quyền vận hành sang nguồn mới |
| **Orphan account** | Tài khoản không có chủ thể/owner hợp lệ |
| **Idempotency** | Xử lý lặp cùng một sự kiện không gây tác động lặp ngoài ý muốn |

Tài liệu chuẩn để tra cứu thêm khi triển khai thực tế:

- **RFC 7643** — System for Cross-domain Identity Management: Core Schema.
- **RFC 7644** — System for Cross-domain Identity Management: Protocol.
- **OpenID Connect Core 1.0** — quy tắc định danh subject và xác thực liên hợp.
- **NIST SP 800-63** — hướng dẫn danh tính số và xác thực, áp dụng theo phiên bản/chính sách tổ chức.
- Tài liệu chính thức của IdP, HRIS và từng ứng dụng về account linking, nhóm, token/session revocation, lifecycle event và đặc tính SCIM; không giả định mọi nhà cung cấp hỗ trợ như nhau.

Một phép thử quyết định chất lượng di trú là: **cùng một người, trước và sau khi thay nguồn, có còn được nhận diện nhất quán, đăng nhập an toàn, chỉ giữ quyền cần thiết và được thu hồi đầy đủ khi vòng đời thay đổi hay không?**

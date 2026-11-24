# Gán employee identifier trong Identity enrollment

Trong quy trình **Identity enrollment** (ghi nhận và thiết lập danh tính), **employee identifier** là mã định danh mà tổ chức dùng để nhận biết một hồ sơ nhân sự trong phạm vi được quy định. Khi HRIS (Human Resources Information System) xác nhận một người gia nhập tổ chức, IAM (Identity and Access Management) cần tiếp nhận hoặc liên kết chính xác mã đó với danh tính số, rồi mới tạo tài khoản và cấp quyền theo chính sách. Mục tiêu không đơn thuần là “điền mã nhân viên vào một trường dữ liệu”, mà là **gắn đúng một hồ sơ nhân sự với đúng chủ thể, tài khoản và quan hệ làm việc có hiệu lực**.

Ví dụ, nhân viên có mã HR **004281** được tiếp nhận vào bộ phận hỗ trợ. IAM cần biết đây là mã thuộc hệ thống HR nào, phạm vi duy nhất của mã là gì, hồ sơ đã được xác minh hay chưa, tài khoản IdP nào thuộc về người đó và các quyền nào được phép cấp. Nếu nhập mã sai hoặc ghép nhầm với tài khoản có sẵn, hệ thống có thể cấp quyền cho người khác. Nếu đổi email mà coi đó là nhân viên mới, hệ thống có thể sinh tài khoản trùng hoặc bỏ sót quyền cũ khi thu hồi.

Bài học nằm trong chương **Identity enrollment** của module quản lý vòng đời danh tính IAM. Nội dung kết nối việc gán mã nhân viên với **Joiner–Mover–Leaver (JML)**, xác minh danh tính, cấp tài khoản, IdP/SSO, SCIM, RBAC/ABAC, đối soát, kiểm toán và giảm quyền truy cập tồn dư. Không có một cách đặt mã nhân viên duy nhất áp dụng cho mọi doanh nghiệp; phạm vi và quy tắc cấp mã phải lấy từ nguồn dữ liệu có thẩm quyền cùng chính sách của tổ chức.

## 1. Employee identifier là gì và không phải là gì?

**Employee identifier** (mã nhân viên) là một giá trị dùng để định danh bản ghi hoặc quan hệ nhân sự trong **một phạm vi đã xác định**. Tùy HRIS, giá trị này có thể được gọi là employee number, personnel number, employee ID hoặc mã nhân sự. Những tên gọi đó **không bảo đảm cùng ngữ nghĩa** giữa các hệ thống: có nơi mã gắn với một con người xuyên suốt thời gian, có nơi mã gắn với từng lần tuyển dụng, hợp đồng, pháp nhân hoặc hồ sơ trả lương.

Một mã nhân viên **không phải** bằng chứng người đang đăng nhập là chủ mã, không phải mật khẩu, không phải quyền truy cập và không thay thế quy trình identity proofing. Nếu một người biết hoặc đoán được mã nhân viên của người khác, họ không được phép dùng mã đó để tự nhận danh tính hay yêu cầu reset MFA mà thiếu các bước xác minh bổ sung.

### 1.1. Phân biệt các định danh thường gặp

| Thuật ngữ | Đối tượng được định danh | Đặc điểm cần nhớ |
| --- | --- | --- |
| **Person identifier** | Một con người trong miền quản lý danh tính. | Có thể ổn định qua nhiều quan hệ lao động nếu tổ chức có quy trình và căn cứ liên kết phù hợp; không phải tổ chức nào cũng có. |
| **Employee identifier / Employee number** | Hồ sơ nhân sự hoặc quan hệ nhân viên theo định nghĩa của HRIS. | Phải biết nguồn cấp, phạm vi duy nhất và quy tắc khi nghỉ việc/tái tuyển. |
| **Employment / Assignment identifier** | Một quan hệ lao động, hợp đồng, vị trí hoặc assignment cụ thể. | Một người có thể có nhiều quan hệ công việc và nhiều mã assignment trong lịch sử. |
| **Identity ID trong IAM/IGA** | Bản ghi danh tính số do nền tảng IAM quản lý. | Dùng làm khóa nội bộ cho liên kết account, chính sách và audit; có thể khác mã HR. |
| **Directory/IdP account ID** | Một đối tượng tài khoản trong directory hoặc IdP. | Thường được hệ thống đích tạo và quản lý; một người có thể có nhiều account. |
| **Username / Email** | Tên dùng để đăng nhập hoặc liên lạc. | Có thể đổi, bị trùng ở miền khác hoặc được tái sử dụng; không nên mặc định là khóa bất biến. |
| **SCIM User.id** | Tài nguyên User trên một SCIM service provider. | Do service provider cấp cho tài nguyên; không phải mặc định là mã nhân viên HR. |
| **SCIM externalId** | Khóa mà provisioning client cung cấp để nhận biết tài nguyên của mình. | Cần xác định đúng client, namespace và quy tắc ánh xạ; không mặc nhiên trùng employee number. |
| **OIDC subject (sub)** | Subject mà OpenID Provider xác định trong phạm vi issuer và quy tắc client. | Không nên coi sub là mã nhân viên; một IdP có thể dùng public hoặc pairwise subject. |
| **Service/workload identity** | Ứng dụng, service account, job hoặc workload phi con người. | Cần mã định danh và owner riêng; thông thường không được gán employee identifier như một nhân viên. |

**Ví dụ:** một người có person ID nội bộ **person-739**, employee number **004281**, IAM identity ID **iam-10018**, IdP account ID **idp-71a** và tài khoản CRM **crm-8821**. Đây là **năm đối tượng/khóa ở các miền khác nhau** nhưng có thể liên kết tới cùng một người. Việc giữ các quan hệ liên kết minh bạch giúp thay đổi username mà không làm mất lịch sử và giúp offboarding tìm đủ các tài khoản cần thu hồi.

### 1.2. Hai cách hiểu employee number có thể cùng hợp lệ

**Mô hình A — mã theo con người:** HRIS cấp một employee number và giữ lại khi nhân viên đổi đơn vị hoặc được tuyển lại, trong phạm vi chính sách. IAM có thể dùng cặp **nguồn + employee number** làm một tín hiệu mạnh để liên kết hồ sơ, nhưng vẫn phải kiểm tra các điều kiện xác minh và xung đột.

**Mô hình B — mã theo quan hệ lao động:** một người rời tổ chức rồi quay lại được cấp employee number mới, hoặc có mã khác nhau ở hai pháp nhân. IAM cần một lớp liên kết person/identity riêng nếu nghiệp vụ cho phép, đồng thời giữ mỗi employment record có trạng thái và thời điểm hiệu lực của nó.

Không nên tự giả định mô hình A rồi áp dụng cho mọi doanh nghiệp. Quy định của HRIS và hợp đồng dữ liệu giữa HR với IAM quyết định cách diễn giải đúng.

## 2. Yêu cầu đối với một employee identifier đáng tin cậy

### 2.1. Phải xác định phạm vi duy nhất (uniqueness scope)

Mã **004281** có thể duy nhất trên toàn tổ chức, hoặc chỉ duy nhất trong một công ty con, tenant HR hay nguồn dữ liệu. Vì vậy, khóa nhận diện có thể là **(sourceSystem, namespace, employeeIdentifier)** thay vì chỉ **employeeIdentifier**.

| Yêu cầu | Ví dụ câu hỏi kiểm tra | Hậu quả nếu bỏ qua |
| --- | --- | --- |
| **Authority** — thẩm quyền cấp mã | HRIS nào cấp mã? Có nguồn nhân sự khác cùng ghi trường này không? | Hai hệ thống tự cấp mã xung đột. |
| **Scope** — phạm vi duy nhất | Mã duy nhất theo tập đoàn, pháp nhân hay tenant? | Hai người cùng mã bị nhập thành một danh tính. |
| **Stability** — tính ổn định | Mã có đổi khi chuyển phòng ban, pháp nhân, hợp đồng hay không? | Cập nhật thuộc tính bị hiểu thành tạo người mới. |
| **Reuse policy** — quy tắc tái sử dụng | Mã của người nghỉ việc có thể cấp lại không? Sau thời gian bao lâu? | Account hoặc quyền lịch sử bị ghép nhầm sang người mới. |
| **Canonical format** — dạng chuẩn | Có số 0 đầu chuỗi? Có phân biệt chữ hoa/thường, dấu cách, dấu gạch? | Chuẩn hóa sai làm thay đổi định danh thực tế. |
| **Evidence** — bằng chứng liên kết | Có hồ sơ nhân sự đã xác nhận và trạng thái hiệu lực không? | Gán mã dựa trên dữ liệu chưa được kiểm chứng. |
| **History** — lịch sử thay đổi | Có lưu mã cũ, mã mới, nguồn, lý do và thời điểm hiệu lực không? | Không truy được tài khoản và quyền đã phát sinh trước thay đổi. |
| **Security & Privacy** | Ai được xem/sửa mã? Mã có thể bị dùng để tra cứu hàng loạt không? | Lộ dữ liệu nhân sự hoặc mở đường giả mạo tài khoản. |

**Mã nhân viên thường nên được xử lý như chuỗi**, ngay cả khi chỉ chứa chữ số. Chuỗi **"004281"** khác **"4281"** nếu nguồn HR coi số 0 đầu là một phần của mã. Không chuyển mã thành số nguyên, tự cắt số 0 hay tự đổi chữ hoa/thường nếu không có quy tắc chuẩn hóa được HR phê duyệt.

### 2.2. Không dùng employee identifier làm bí mật xác thực

Mã nhân viên có thể xuất hiện trên thẻ, phiếu lương, tài liệu nội bộ hoặc URL. Vì thế:

- Không dùng employee number làm **mật khẩu**, yếu tố MFA hoặc câu trả lời xác minh duy nhất.
- Không dùng việc nhập đúng employee number để tự liên kết account IdP hoặc khôi phục quyền.
- Không cấp role/entitlement chỉ vì client tự khai một employee number trong request.
- Tránh hiển thị mã trong URL, thông báo lỗi hoặc log ngoài phạm vi cần thiết; hạn chế khả năng dò mã liên tiếp.
- Luôn xác định **issuer/source** và kiểm tra quyền của hệ thống gửi thay đổi; dữ liệu từ nguồn chưa tin cậy chỉ nên được coi là thông tin cần xác minh.

Các yêu cầu này đặc biệt quan trọng khi tích hợp nhiều HRIS, hệ thống nhà thầu hoặc quy trình self-service onboarding.

## 3. Ai thực sự gán mã nhân viên?

Trong kiến trúc thông dụng, **HRIS hoặc quy trình quản lý nhân sự được ủy quyền** cấp employee number. IAM tiếp nhận, kiểm tra và liên kết mã tới identity record. IAM có thể cấp **identity ID nội bộ riêng**, nhưng không nên tự tạo một employee number “thay HR” nếu hợp đồng dữ liệu không trao quyền đó cho IAM.

Các vai trò điển hình:

| Vai trò / Thành phần | Trách nhiệm |
| --- | --- |
| **HR / Authoritative HRIS** | Xác nhận hồ sơ, quan hệ lao động, employee number, trạng thái và thời điểm hiệu lực. |
| **Identity proofing / Enrollment owner** | Xác minh đúng người/hồ sơ theo mức rủi ro, xử lý bằng chứng thiếu hoặc mâu thuẫn. |
| **IAM/IGA** | Chuẩn hóa theo quy tắc, kiểm tra trùng, tạo/liên kết identity, tính quyền và quản trị workflow. |
| **Directory / IdP** | Quản lý tài khoản xác thực; lưu ID tài khoản riêng và các thuộc tính được phép đồng bộ. |
| **Provisioning connector / SCIM client** | Gửi thay đổi đã được phép tới tài nguyên và account của ứng dụng đích. |
| **Application owner** | Xác định entitlement nào phù hợp với vai trò, trạng thái và thuộc tính nhân viên. |
| **Security / Audit / Data stewardship** | Kiểm tra việc cấp nhầm, quyền tồn dư, dấu vết thay đổi và điều kiện bảo vệ dữ liệu. |

Một yêu cầu tuyển dụng đã được tạo **không đồng nghĩa** việc đã xác minh danh tính hoặc có quan hệ làm việc được phép kích hoạt. Tùy chính sách, hệ thống có thể chuẩn bị trước identity/account ở trạng thái chờ, nhưng việc **kích hoạt đăng nhập và cấp quyền** phải dựa vào mốc nghiệp vụ được phê duyệt.

## 4. Quy trình gán và liên kết employee identifier khi enrollment

~~~mermaid
flowchart TD
    HR["HRIS: hồ sơ đã được xác nhận + employee number"] --> VAL["IAM kiểm tra nguồn, định dạng, phạm vi, hiệu lực"]
    VAL --> LOOKUP{"Đã tồn tại binding cùng khóa?"}
    LOOKUP -->|Không| LINK{"Có bằng chứng liên kết person cũ?"}
    LOOKUP -->|Có, nhất quán| EXIST["Dùng identity hiện có"]
    LOOKUP -->|Có, mâu thuẫn| REVIEW["Dừng liên kết và rà soát thủ công"]
    LINK -->|Có, được duyệt| EXIST
    LINK -->|Không| NEW["Tạo IAM identity mới"]
    EXIST --> BIND["Lưu binding có lịch sử, kiểm tra uniqueness"]
    NEW --> BIND
    BIND --> POLICY["Tính desired access theo JML, RBAC/ABAC, phê duyệt"]
    POLICY --> PROV["Tạo/liên kết account tại IdP và ứng dụng"]
    PROV --> VERIFY["Readback/đối soát tài khoản, quyền và audit"]
    VERIFY -->|Sai lệch| REMED["Ticket lỗi, owner, khắc phục"]
    VERIFY -->|Khớp| DONE["Enrollment được xác nhận hoàn tất"]
    REMED --> VERIFY
~~~

### Bước 1 — Nhận bản ghi từ nguồn có thẩm quyền

Tối thiểu cần xác định **source system**, **employee identifier**, **phạm vi mã**, **identity/relationship status**, **effective date**, và một tham chiếu hồ sơ đủ tin cậy để kiểm tra. Nhiều nguồn có thể có mã trùng; không được trộn chỉ vì giá trị chuỗi giống nhau.

Ví dụ, cùng một chuỗi **004281** ở HRIS-A của pháp nhân A và HRIS-B của pháp nhân B có thể là hai người khác nhau. Định danh an toàn phải giữ nguồn/namespace trong khóa liên kết.

### Bước 2 — Xác minh và kiểm tra tính hợp lệ

Kiểm tra hồ sơ có hợp lệ theo quy trình nhân sự không; mã có tuân thủ dạng và phạm vi do nguồn công bố; trạng thái có cho phép tạo identity ở thời điểm này không; event có bị trùng, đến muộn hoặc thay thế bằng phiên bản mới không.

**Identity proofing** xác minh một con người theo bằng chứng phù hợp; việc mã nhân viên xuất hiện trong HRIS **không tự động** thực hiện proofing. Nếu thiếu hồ sơ, nguồn không đáng tin hoặc nhiều bản ghi mâu thuẫn, workflow phải chuyển sang xác minh chứ không “đoán” người phù hợp nhất.

### Bước 3 — Kiểm tra trùng và liên kết với identity có sẵn

IAM tìm mapping của khóa **(sourceSystem, namespace, employeeIdentifier)**. Nếu khóa đã gắn với identity phù hợp, xử lý như một thay đổi hoặc cập nhật hiện có. Nếu chưa có, kiểm tra liệu có liên kết person-level đã được xác minh, ví dụ một trường hợp rehire. Nếu chưa đủ bằng chứng, tạo danh tính mới theo quy trình; nếu có dấu hiệu collision hoặc hai identity cùng nhận một mã, **không tự merge**.

Tuyệt đối không coi **email giống nhau**, **tên trùng nhau** hoặc **ngày sinh trùng nhau** là đủ để tự kết luận hai hồ sơ là cùng một người. Việc merge/split identity ảnh hưởng quyền truy cập và lịch sử kiểm toán, nên cần bằng chứng, quy trình phê duyệt và khả năng phục hồi thích hợp.

### Bước 4 — Ghi binding và lịch sử

Lưu employee identifier như một **external identity binding** có source và phạm vi. Nếu một employee number được HR thay đổi, cần biết **giá trị cũ**, **giá trị mới**, **thời điểm hiệu lực**, **nguyên nhân và hệ thống đã đồng bộ**; không xóa dấu vết gắn với tài khoản cũ.

Phần mềm cần ngăn xung đột đồng thời: hai yêu cầu enrollment đến cùng lúc không được tạo hai IAM identity cho một khóa được xác minh là duy nhất. Kiểm tra bằng truy vấn ở tầng ứng dụng nên đi cùng ràng buộc nhất quán hoặc thao tác ghi nguyên tử theo thiết kế của kho dữ liệu.

### Bước 5 — Cấp account/quyền theo điều kiện, rồi xác minh

Sau khi identity được liên kết, IAM mới tính **desired access** từ trạng thái lao động, role, department, location và các thuộc tính được xác minh. **RBAC** có thể cấp quyền nền tảng theo vai trò; **ABAC** có thể kiểm tra điều kiện bổ sung ở tài nguyên hoặc thời điểm truy cập.

Việc gán employee identifier **không tự nó cấp quyền**. Hệ thống phải tách rõ:

- **Identity bound**: đã xác định đúng mã HR ↔ identity.
- **Account provisioned**: IdP/ứng dụng đã tạo hoặc liên kết tài khoản.
- **Access granted**: các entitlement hợp lệ đã được áp dụng.
- **Verified**: trạng thái thực tế tại đích được đối soát và phù hợp quyết định.

Nếu một connector bị lỗi, cần ghi nhận lỗi/owner xử lý; không đánh dấu toàn bộ quy trình thành công chỉ vì IAM đã lưu employee number.

## 5. Mô hình dữ liệu tham khảo

### 5.1. Bản ghi identity và binding

~~~json
{
  "identity": {
    "identityId": "iam-person-739",
    "type": "HUMAN",
    "lifecycleState": "PENDING_START"
  },
  "employmentBinding": {
    "sourceSystem": "HRIS-A",
    "namespace": "legal-entity-VN01",
    "employeeIdentifier": "004281",
    "employmentRecordId": "hr-contract-1901",
    "effectiveFrom": "2026-08-01T00:00:00+07:00",
    "effectiveTo": null,
    "verificationStatus": "VERIFIED",
    "sourceVersion": 18
  },
  "accountBindings": [
    {
      "targetSystem": "CorporateIdP",
      "targetAccountId": "idp-71a",
      "accountState": "STAGED"
    }
  ]
}
~~~

Đây là **schema minh họa do bài học xây dựng**, không phải payload của một chuẩn IAM. Các trường được tách để tránh dùng một giá trị cho nhiều mục đích:

- **identityId** là khóa quản lý danh tính nội bộ IAM.
- **employeeIdentifier** là mã nhân viên đúng theo ngữ nghĩa HRIS.
- **employmentRecordId** định danh quan hệ/hồ sơ nhân sự nếu nguồn cung cấp.
- **targetAccountId** là khóa tài khoản do IdP hoặc ứng dụng quản lý.
- **effectiveFrom/effectiveTo** giúp xác định binding có hiệu lực theo thời gian.
- **sourceVersion** hỗ trợ nhận biết cập nhật cũ/mới nếu nguồn có version có ngữ nghĩa đáng tin.

Trong hệ thống thực tế có thể cần thêm person identity, nhiều employment binding, nhiều account, lịch sử phê duyệt và các trạng thái ngoại lệ. Không nên “nhồi” mọi quan hệ vào duy nhất trường employee number.

### 5.2. Quy tắc uniqueness và xử lý concurrency

Một thiết kế hợp lý có thể tạo khóa tra cứu gồm **sourceSystem + namespace + employeeIdentifier** và ràng buộc sao cho trong cùng thời điểm hiệu lực, một khóa không đồng thời được liên kết tới hai identity xung đột. Nếu HR có chính sách tái sử dụng mã hoặc nhiều hợp đồng, khóa và lịch sử hiệu lực phải phản ánh đúng mô hình đó; không áp đặt tùy tiện uniqueness toàn thời gian khi nghiệp vụ không cho phép.

Pseudocode dưới đây minh họa thứ tự kiểm soát:

~~~text
enroll(hrEvent):
    require authenticatedAuthoritativeSource(hrEvent)
    require validEmployeeIdentifier(hrEvent)

    key = (
        hrEvent.sourceSystem,
        hrEvent.namespace,
        canonicalizeByApprovedSourceRules(hrEvent.employeeIdentifier)
    )

    begin transaction
        if eventAlreadyProcessed(hrEvent.eventId):
            return recordedOutcome(hrEvent.eventId)

        current = findEffectiveBinding(key, hrEvent.effectiveAt)

        if current conflicts with verified person or employment evidence:
            recordReviewRequired(hrEvent.eventId, "IDENTITY_COLLISION")
            commit
            return REVIEW_REQUIRED

        identity = current.identity
                   or resolvePreviouslyVerifiedPerson(hrEvent)
                   or createNewIdentity()

        saveBindingAtomically(identity, key, hrEvent.sourceVersion)
        recordDecisionAndSourceEvidence(hrEvent.eventId, identity)
    commit

    enqueueProvisioningForDesiredState(identity, hrEvent.eventId)
    return PENDING_TARGET_VERIFICATION
~~~

Pseudocode **không phải triển khai production**. Hệ thống thực cần xác thực nguồn, quản lý transaction/ràng buộc, quy tắc hồi phục, bất biến về identity linking, xử lý race condition và mô hình event ordering phù hợp. Việc tạo account ở ứng dụng ngoài transaction dữ liệu IAM phải được quản lý bằng tác vụ có trạng thái, idempotency/retry và đối soát sau thực thi.

### 5.3. Vì sao không dùng employee number làm khóa chính cho mọi bảng?

Giả sử tất cả entitlement và audit đều tham chiếu trực tiếp employee number. Nếu HR phải đổi mã do hợp nhất pháp nhân hoặc người được tái tuyển với mã mới, nhiều liên kết cần thay đổi và có nguy cơ mất lịch sử. Một **identity ID nội bộ không phụ thuộc định dạng mã HR** giúp duy trì liên kết, còn employee identifier được lưu như binding có source và thời hạn.

Điều đó không có nghĩa identity ID nội bộ tự động chứng minh hai HR record là một người. Việc liên kết vẫn cần kiểm soát và bằng chứng xác minh.

## 6. Ánh xạ employee identifier tới IdP, SSO và SCIM

### 6.1. IdP và SSO sử dụng định danh của miền xác thực

Directory/IdP thường có account ID riêng, username và các thuộc tính mở rộng. IAM có thể đồng bộ employee number để tra cứu và đối soát **nếu việc chia sẻ được phép và cần thiết**. Tuy nhiên:

- **IdP account ID** không bắt buộc trùng employee number.
- **Username/email** có thể đổi khi người dùng đổi tên, domain hoặc phòng ban.
- **OIDC sub** cần được hiểu trong ngữ cảnh issuer và cách IdP tạo subject; không dùng employee number làm giả định mặc định cho sub.
- **SAML NameID** có nhiều định dạng và vòng đời khác nhau; không tự suy ra nó là khóa HR bất biến.
- **SSO xác thực** và chuyển thông tin nhận dạng; nó không tự bảo đảm tài khoản ứng dụng đã được cấp quyền hợp lệ hoặc được thu hồi.

Một ứng dụng cần identity correlation phải dùng mapping đã được thiết kế giữa subject tại IdP và account trong ứng dụng, thay vì chỉ so khớp tên hiển thị hoặc email.

### 6.2. SCIM có employeeNumber nhưng không bắt buộc mọi ứng dụng hỗ trợ

Trong **SCIM 2.0**, thuộc tính **employeeNumber** được định nghĩa trong **Enterprise User extension** (RFC 7643), không phải một thuộc tính bắt buộc trong User core schema. Cần kiểm tra ứng dụng đích có hỗ trợ extension này, cách mapping và giới hạn dữ liệu của ứng dụng.

Ba trường thường gặp với vai trò khác nhau:

| Trường SCIM | Ý nghĩa | Cách sử dụng thận trọng |
| --- | --- | --- |
| **User.id** | ID tài nguyên do SCIM service provider cấp. | Dùng cho thao tác trên tài nguyên ở chính provider đó; không gán lại bằng mã HR theo giả định. |
| **externalId** | ID tham chiếu do provisioning client cung cấp cho tài nguyên. | Có thể dùng IAM identity ID hoặc khóa được thiết kế riêng theo hợp đồng kết nối. |
| **Enterprise User.employeeNumber** | Mã nhân viên trong Enterprise User extension. | Có thể chứa employee identifier từ HR nếu ứng dụng hỗ trợ và việc đồng bộ phù hợp. |

Ví dụ **payload tạo User minh họa** cho một provider hỗ trợ Enterprise User extension:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "userName": "nhanvien.4281@example.invalid",
  "externalId": "iam-person-739",
  "active": false,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "004281",
    "department": "CustomerSupport"
  }
}
~~~

Trường **active: false** ở ví dụ biểu diễn account được chuẩn bị nhưng chưa kích hoạt; cách thực tế phải theo chính sách và khả năng provider. Phản hồi tạo tài nguyên thường có **id của provider** cần lưu về account binding. Mã HR nên được truyền dưới dạng chuỗi; không mặc nhiên biến nó thành username hoặc khóa truy cập.

Nếu provider chỉ hỗ trợ SCIM core hoặc không hỗ trợ employeeNumber, IAM có thể chỉ lưu mapping nội bộ và gửi thuộc tính thật sự được ứng dụng hỗ trợ. Không nên lạm dụng các field khác như department, costCenter hoặc địa chỉ để chứa employee number.

### 6.3. API riêng và ứng dụng chưa hỗ trợ SCIM

Với ứng dụng dùng API riêng hoặc provisioning thủ công, vẫn cần:

1. Khóa tài khoản tại ứng dụng và mapping ổn định với IAM identity ID.
2. Quy tắc rõ ràng để tìm account khi email/username thay đổi.
3. Kết quả tạo/cập nhật/khóa account có log và mã tác vụ.
4. Phát hiện account trùng hoặc orphaned account sau đồng bộ.
5. Đối soát định kỳ vì quyền có thể được admin cấp trực tiếp ngoài IAM.

Định danh chính xác chỉ giải quyết câu hỏi **“đây là account của ai?”**; quyền được phép sử dụng phải tiếp tục được quyết định bởi chính sách và phê duyệt.

## 7. Joiner–Mover–Leaver tác động tới employee identifier như thế nào?

### 7.1. Joiner: tạo liên kết và kích hoạt đúng thời điểm

**Tình huống:** HRIS tạo employee number **004281** cho nhân viên mới, ngày vào làm 01/08. Trước ngày đó, IAM có thể ghi nhận identity ở trạng thái chờ, kiểm tra dữ liệu và chuẩn bị account tùy chính sách. Khi đủ điều kiện:

1. Nhận sự kiện onboarding từ HRIS có thẩm quyền.
2. Xác minh/chấp nhận bằng chứng về người và quan hệ lao động.
3. Kiểm tra trùng khóa nhân sự trong đúng namespace.
4. Gán hoặc liên kết identity ID nội bộ và employee identifier.
5. Tính baseline access, xử lý phê duyệt quyền nhạy cảm.
6. Provisioning tới IdP/SCIM/API, thiết lập yêu cầu MFA và xác minh kết quả.

**Employee identifier đã tồn tại** không có nghĩa phải cấp access ngay lập tức; HR có thể tạo hồ sơ trước ngày bắt đầu.

### 7.2. Mover: thông thường giữ định danh và đổi quyền

**Tình huống:** một nhân viên chuyển từ hỗ trợ sang tài chính nhưng vẫn cùng quan hệ lao động. Employee number thường **không cần thay đổi**, trừ khi chính sách HR có quy định khác. IAM cập nhật thuộc tính vai trò, department hoặc location, tính lại desired access, **gỡ quyền cũ không còn phù hợp** rồi cấp quyền mới sau các bước phê duyệt.

Mã nhân viên giúp hệ thống xác định sự kiện thuộc đúng identity dù người đó đổi email hoặc username. Trong quyền quản trị, cần kiểm tra **Segregation of Duties (SoD)** và rà soát quyền thừa; việc giữ mã nhân viên ổn định không cho phép giữ tất cả quyền của role cũ.

**Biến thể:** chuyển sang pháp nhân khác có thể sinh employment record hoặc employee identifier mới theo HRIS. Khi đó không nên tự coi là người mới hoặc tự đồng nhất hai hồ sơ; IAM phải dùng bằng chứng person-linking và quy tắc chuyển giao đã được phê duyệt.

### 7.3. Leaver: vô hiệu hóa quyền nhưng vẫn giữ liên kết kiểm toán cần thiết

Khi HR xác nhận người nghỉ việc, IAM dùng identity và account bindings để tìm **toàn bộ account liên quan**, rồi disable/deprovision theo chính sách, gỡ entitlement, xử lý session/token/credential nếu cần và xác minh ở ứng dụng đích.

Không nên xóa hoặc tái sử dụng employee number trong kho IAM một cách làm đứt lịch sử kiểm toán. Tuy nhiên, việc **lưu giữ** identifier phải có căn cứ và thời hạn theo chính sách bảo vệ dữ liệu; không mặc định giữ mọi dữ liệu mãi mãi.

Quy trình Leaver hoàn tất khi các đường truy cập phải chặn đã được **xác minh**, không phải khi trường trạng thái tại HRIS vừa đổi thành terminated.

### 7.4. Rehire: câu hỏi “người cũ” hay “hồ sơ mới”?

Một người từng làm việc quay lại sau hai năm. Các khả năng:

| Chính sách HR | Xử lý enrollment cần thiết |
| --- | --- |
| **Cấp lại cùng employee number** | Kiểm tra lịch sử và bằng chứng cùng người; tái thiết lập quan hệ hiệu lực; tính lại quyền từ đầu. |
| **Cấp employee number mới** | Xác minh liên kết với person/identity cũ khi được phép; ghi binding mới; không dựa trên email hoặc tên để tự merge. |
| **Mã cũ được tái sử dụng cho người khác** | Phải phân biệt bằng source, namespace, lịch sử hiệu lực và thông tin đã xác minh; không gán account/quyền của người trước cho người mới. |
| **Người có nhiều hợp đồng đồng thời** | Có thể có nhiều employment/assignment IDs; quyết định dùng một hay nhiều identity/accounts theo chính sách, bảo đảm phân biệt quyền từng quan hệ. |

Rehire **không phải** lý do khôi phục mặc định toàn bộ quyền cũ. Quyền mới cần được đánh giá theo trạng thái, role, phạm vi công việc và phê duyệt hiện tại.

## 8. Xử lý những trường hợp khó khi gán mã

### 8.1. Trùng mã giữa các nguồn

HRIS-A và HRIS-B cùng gửi **004281** cho hai nhân viên khác nhau. Nếu IAM chỉ tra theo chuỗi employeeNumber, hệ thống có thể gắn nhầm hai người thành một identity và làm lộ quyền. Cần dùng **source/namespace** theo quy tắc định danh, đối soát dữ liệu và chặn các thao tác merge thiếu chứng cứ.

### 8.2. Đổi employee number do sửa dữ liệu hoặc chuyển hệ thống

Khi HR đổi mã từ **004281** thành **004982**, hệ thống phải xác định đây là **cùng một người/quan hệ đã được xác minh**, một bản ghi nhân sự mới hay việc sửa lỗi nhập dữ liệu. Quy trình cần lưu lịch sử alias/binding cũ và mới, cập nhật các liên kết kỹ thuật có phụ thuộc mã cũ và kiểm tra lại account trong ứng dụng. Nếu một hệ thống dùng employee number làm username, thay đổi phải được lập kế hoạch và phối hợp để tránh đứt đăng nhập.

### 8.3. Sự kiện đến trễ hoặc bị phát lại

Giả sử HR gửi phiên bản 18 cập nhật mã hợp lệ rồi một hàng đợi phát lại phiên bản 17. Nếu hệ thống ghi đè theo thứ tự nhận, mapping có thể bị đảo ngược và cấp quyền sai. Khi nguồn hỗ trợ **event ID, source version và effective time**, IAM cần quy tắc xử lý idempotency/ordering, giữ lịch sử và xác minh trạng thái hiện hành tại nguồn.

### 8.4. Hai hồ sơ trông giống một người

Những trường hợp tên, email hoặc số điện thoại giống nhau có thể là lỗi nhân sự, trường hợp sử dụng lại dữ liệu liên hệ hoặc hai cá nhân khác nhau. Không được tự gộp identity dựa trên điểm tương đồng đơn giản. Cần xác minh bằng nguồn có thẩm quyền và quy trình có người chịu trách nhiệm, nhất là khi một hồ sơ có quyền đặc quyền hoặc dữ liệu nhạy cảm.

### 8.5. Nhân viên chưa có mã

Một số HRIS cấp mã muộn hơn ngày khởi tạo hồ sơ. Tổ chức có thể dùng **provisional identity ID** do IAM tạo ở trạng thái chờ, gắn với yêu cầu nhân sự hợp lệ, và bổ sung employee identifier khi HR cấp. Quyền cấp trong giai đoạn chờ cần được chính sách hạn chế rõ ràng; không dùng giá trị giả như **000000** cho mọi nhân viên vì sẽ tạo collision.

### 8.6. Nhà thầu và tài khoản phi con người

Không phải đối tượng IAM nào cũng có employee number. Nhà thầu có thể có **contractor ID** hoặc **partner identity ID** và người bảo trợ; workload/service account cần **workload ID**, owner, mục đích và credential lifecycle riêng. Nếu chủ sở hữu service account nghỉ việc, IAM cần chuyển ownership và đánh giá quyền service chứ không xóa account dựa trên employee identifier của người chủ cũ.

## 9. Accountability, audit và bảo vệ employee identifier

Một quyết định liên kết employee number nên có bằng chứng đủ để trả lời: **ai hoặc nguồn nào cung cấp mã, ai xác minh, mã liên kết với identity nào, khi nào có hiệu lực, tài khoản nào đã được tạo và quyền nào đã được cấp/thu hồi?**

| Bằng chứng | Tác dụng |
| --- | --- |
| Source system, namespace, event ID, bản ghi HR tham chiếu | Xác định căn cứ và phạm vi mã được cấp. |
| Employee identifier trước/sau, identity ID, effective time | Truy vết thay đổi mã mà không nhầm đối tượng. |
| Kết quả proofing/correlation và người phê duyệt ngoại lệ | Giải thích vì sao một mã được gắn với một identity có sẵn. |
| IdP/app account IDs, connector task ID, kết quả SCIM/API | Chứng minh account nào được tạo, cập nhật hoặc khóa. |
| Policy/version, role/ABAC attributes liên quan, approval | Giải thích quyền nào được phép và lý do. |
| Reconciliation/verification và ticket xử lý lỗi | Chứng minh trạng thái thực tế phù hợp quyết định. |

### 9.1. Ví dụ bản ghi sự kiện liên kết đã xác nhận

~~~json
{
  "eventId": "identity-enrollment-612",
  "eventType": "EMPLOYEE_IDENTIFIER_BOUND",
  "source": {
    "system": "HRIS-A",
    "namespace": "legal-entity-VN01",
    "employeeIdentifier": "004281",
    "recordRef": "hr-contract-1901",
    "sourceVersion": 18
  },
  "target": {
    "identityId": "iam-person-739",
    "bindingStatus": "VERIFIED"
  },
  "decision": {
    "method": "AUTHORITATIVE_SOURCE_MATCH",
    "policyRef": "identity-link-policy-v3",
    "decidedAt": "2026-07-23T09:10:00+07:00"
  },
  "nextStep": "PROVISION_ACCOUNTS_AFTER_EFFECTIVE_DATE",
  "correlationId": "joiner-workflow-739"
}
~~~

Đây là ví dụ nội bộ; nó không thay thế event schema chuẩn của một sản phẩm. Khi phát sinh lỗi, cần lưu các sự kiện riêng cho **review required**, **correction**, **relink** hoặc **reconciliation failure**, để không che mất quyết định trước đó.

### 9.2. Bảo vệ dữ liệu và dấu vết liên kết

- **Data minimization:** chỉ truyền employee identifier đến hệ thống thực sự cần; nhiều ứng dụng chỉ cần IAM ID hoặc account mapping đã liên kết.
- **Access control:** giới hạn người có thể đọc/sửa mã hoặc tự liên kết identity; thao tác quan trọng cần phê duyệt hoặc phân tách nhiệm vụ thích hợp.
- **Audit integrity:** ghi sự kiện sửa mapping và thay đổi owner; bảo vệ log khỏi chỉnh/xóa trái phép.
- **Chống enumeration:** API tra cứu theo employee number cần xác thực, phân quyền, giới hạn tốc độ và thông báo lỗi không tiết lộ quá mức.
- **Không log bí mật xác thực:** employee number không nên được xem là secret, nhưng không vì thế được phép ghi token, password hoặc giấy tờ proofing chi tiết vào log.
- **Retention có chủ đích:** lịch sử được lưu đủ cho đối soát, kiểm toán hoặc nghĩa vụ áp dụng và xử lý/xóa theo chính sách hợp lệ.

Đặc biệt, đừng công khai endpoint cho phép đổi account ID chỉ bằng employee number. Kẻ tấn công có thể biết mã và tìm cách liên kết account của mình với hồ sơ HR của người khác để nhận quyền.

## 10. Ví dụ xuyên suốt: Joiner, đổi email, Mover và Leaver

**Bối cảnh:** HRIS-A cấp mã **004281** cho Hà, thuộc nhóm vận hành tại văn phòng HCM. IAM tạo identity nội bộ **iam-person-739**; IdP cấp account **idp-71a**.

| Thời điểm | Sự kiện | Điều hệ thống phải bảo đảm |
| --- | --- | --- |
| **Joiner** | HR xác nhận nhân viên và mã 004281, có ngày bắt đầu. | Verify nguồn và liên kết đúng identity; tạo account theo thời điểm và quyền được duyệt. |
| **Đổi email** | Email công ty của Hà thay đổi. | Không tạo identity mới; cập nhật username/địa chỉ trên các target hỗ trợ, giữ audit liên kết với identity/account ID. |
| **Mover** | Hà chuyển từ vận hành sang kiểm toán nội bộ. | Cùng employee number trong chính sách HR này; gỡ quyền vận hành và cấp quyền mới sau kiểm tra SoD, least privilege. |
| **Leaver** | HR xác nhận Hà kết thúc hợp đồng. | Tìm tất cả account qua binding, disable/revoke quyền/credential cần thiết và xác minh target. |
| **Rehire** | Hà quay lại theo mã HR mới hoặc cũ tùy chính sách. | Xác minh liên kết person, tạo quan hệ hiệu lực mới và tính lại quyền; tránh khôi phục quyền cũ tự động. |

Giả sử sau Mover, tài khoản ứng dụng cũ vẫn còn role quản trị vì connector lỗi. Employee identifier giúp IAM xác định đúng account để kiểm tra, nhưng **không tự thu hồi quyền**. IAM phải đo desired state, thực thi deprovisioning và xác minh actual state; lỗi cần ticket và owner. Nếu sau Leaver, IdP account đã disable nhưng ứng dụng có local account hoặc session độc lập, vẫn có thể còn **residual access** cần xử lý.

Một cách nhìn dữ liệu xuyên suốt:

~~~text
HRIS-A / legal-entity-VN01 / employeeIdentifier "004281"
           |
           v
IAM identity "iam-person-739"
           |
           +--- IdP account "idp-71a" ------> SSO / MFA
           |
           +--- CRM account "crm-8821" -----> Entitlements & sessions
           |
           +--- Git account "git-5023" -----> Repositories & access tokens
           |
           +--- Audit events --------------> Decisions / execution / verification
~~~

Đối với mỗi target, account ID và entitlement cần được đối soát theo hệ thống. Không thể chỉ tìm một chuỗi employee number trên mọi ứng dụng rồi coi đó là bằng chứng định danh chính xác.

## 11. Các sai lầm triển khai thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Coi email hoặc username là employee identifier bất biến. | Đổi email tạo identity trùng hoặc mất mapping. | Tách HR employee number, IAM identity ID và account ID. |
| Chỉ lưu employee number, không lưu nguồn/namespace. | Trùng mã giữa HRIS/pháp nhân bị merge sai. | Dùng khóa định danh đủ phạm vi đã được HR xác nhận. |
| Chuyển employee number kiểu chuỗi thành số. | Mất số 0 đầu, gây lỗi tìm kiếm và liên kết. | Giữ chuỗi đúng hợp đồng dữ liệu. |
| IAM tự phát mã HR khi chưa được giao thẩm quyền. | Nguồn dữ liệu nhân sự bị phân mảnh và mâu thuẫn. | HRIS cấp mã; IAM chỉ cấp ID nội bộ hoặc mã tạm có ngữ nghĩa riêng. |
| Tự merge theo tên/email giống nhau. | Trộn quyền và lịch sử của hai người. | Bắt buộc kiểm tra proofing, evidence và quy trình conflict review. |
| Dùng employee number như yếu tố xác thực. | Dễ đoán, dễ lộ, tăng nguy cơ chiếm tài khoản. | AuthN/MFA tách khỏi mã nhân sự. |
| Coi SCIM id/externalId là employeeNumber. | Gắn sai ngữ nghĩa, thay đổi ID làm đứt account correlation. | Dùng mapping theo schema thực tế và hợp đồng connector. |
| Cứ có mã là tự cấp tất cả baseline quyền. | Cấp quyền trước ngày làm việc hoặc cho hồ sơ không hợp lệ. | Kiểm tra trạng thái, effective time, role/policy và approval. |
| Mover chỉ thêm role mới, không gỡ role cũ. | Tích lũy quyền và vi phạm SoD. | Tính desired state mới và đối soát quyền cũ/mới. |
| Leaver xóa mọi mapping ngay. | Mất bằng chứng kiểm toán và khó phát hiện orphaned account. | Chặn truy cập, giữ lịch sử theo retention và reconcile các target. |
| Hai worker xử lý cùng sự kiện tạo hai identity. | Duplicate identities/accounts, quyền phân tán. | Idempotency, ràng buộc khóa và ghi nguyên tử. |
| Dùng mã nhân viên của owner cho service account. | Vòng đời workload phụ thuộc sai vào một nhân sự. | Workload identity và ownership được quản lý riêng. |

## 12. Checklist thiết kế và câu hỏi thực hành

Trước khi đưa quy trình **gán employee identifier** vào sản xuất, nên trả lời được:

1. **Nguồn:** hệ thống nào có thẩm quyền cấp employee number? Có nhiều nguồn hoặc pháp nhân không?
2. **Ngữ nghĩa:** mã đại diện person, employment record hay một quan hệ nghiệp vụ khác? Có được tái sử dụng không?
3. **Định dạng:** phạm vi duy nhất, số 0 đầu, độ dài, phân biệt hoa/thường và quy tắc canonicalization được xác định chưa?
4. **Proofing:** đã có bằng chứng danh tính/hồ sơ hợp lệ chưa? Ai xử lý hai hồ sơ mâu thuẫn hoặc trùng người?
5. **Binding:** IAM identity ID, employee number, nguồn, account IDs và lịch sử hiệu lực có tách biệt rõ không?
6. **Concurrency:** event trùng, đến trễ hoặc hai thao tác đồng thời có làm tạo nhiều identity cho cùng người không?
7. **Provisioning:** các ứng dụng và SCIM connector có thật sự hỗ trợ thuộc tính/mapping dự kiến không?
8. **JML:** Joiner có được kích hoạt đúng thời điểm? Mover có gỡ quyền cũ? Leaver có tìm đủ account để thu hồi và đối soát?
9. **Governance:** có log nguồn, quyết định liên kết, phê duyệt, kết quả thực thi và owner sửa lỗi không?
10. **An toàn:** employee identifier có bị dùng làm bí mật xác thực hoặc bị đưa quá rộng vào log/API không?

### Tình huống A — Hai HRIS cùng một mã

HRIS-A và HRIS-B cùng phát employee number **004281** nhưng thuộc hai người khác nhau. Một phép so khớp chỉ theo số sẽ có vấn đề gì? Hãy đề xuất khóa định danh, bước kiểm tra và cách ngăn cấp quyền sai khi hai sự kiện đến gần nhau.

### Tình huống B — Tái tuyển dụng với mã mới

Nhân viên từng có employee number **004281**, sau ba năm quay lại với mã **009731**. Email cũng đã khác. Hãy giải thích vì sao không được tạo liên kết person tự động chỉ bằng tên, và những bằng chứng/quan hệ nào phải được giữ nếu quyết định nối hai employment record vào cùng một identity.

### Tình huống C — SCIM provider không hỗ trợ Enterprise User

Ứng dụng đích chỉ hỗ trợ core User schema và cấp **User.id** riêng. IAM muốn provisioning account cho nhân viên có employee number **004281**. Hãy xác định nên lưu mapping ở đâu, các field nào có thể dùng theo hợp đồng, và vì sao không được ép employee number vào một field không đúng ngữ nghĩa.

### Tình huống D — Thu hồi quyền sau Mover

HR đổi role của Hà từ vận hành sang kiểm toán. Employee number không đổi, IdP account vẫn tồn tại, nhưng ứng dụng Git giữ quyền admin cũ. Hãy phân biệt trách nhiệm của **identity binding**, **policy evaluation**, **deprovisioning** và **reconciliation**; xác định bằng chứng cần có trước khi kết luận quyền đã được thu hồi.

**Điểm cần ghi nhớ:** Employee identifier là **khóa nhân sự có nguồn và phạm vi xác định**, được gán hoặc xác nhận theo quy trình HR có thẩm quyền. IAM cần **liên kết đúng người và quan hệ làm việc**, giữ **identity ID, employee number và account ID** như các khái niệm khác nhau, xử lý an toàn việc trùng/đổi/tái tuyển, rồi dùng trạng thái và chính sách JML để **cấp, rà soát và thu hồi quyền có kiểm chứng**. Việc “đã có mã nhân viên” là điểm bắt đầu của quản lý danh tính có trách nhiệm, không phải bằng chứng tự đủ để đăng nhập hay được truy cập.

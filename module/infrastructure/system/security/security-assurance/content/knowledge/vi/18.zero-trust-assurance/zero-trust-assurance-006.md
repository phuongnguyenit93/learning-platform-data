# Device trust trong Zero Trust assurance: đánh giá độ tin cậy của thiết bị bằng bằng chứng

Một nhân viên đăng nhập vào nền tảng quản lý tài chính bằng tài khoản hợp lệ, đã xác thực đa yếu tố và được cấp role xem báo cáo. Tuy nhiên, máy tính của họ không còn nhận bản vá, tác nhân EDR đã ngừng hoạt động, trình duyệt đang chạy trên một hệ điều hành không được quản lý. Ở chiều ngược lại, một laptop công ty vừa kiểm tra compliance thành công nhưng kẻ tấn công đã đánh cắp session của người dùng và thử gọi API xuất dữ liệu. Trong cả hai trường hợp, việc hỏi đơn giản **“đây có phải thiết bị công ty không?”** không đủ để quyết định truy cập.

**Device trust** là năng lực đánh giá mức độ đáp ứng yêu cầu bảo mật của thiết bị đang tham gia một phiên truy cập và sử dụng kết quả như một **tín hiệu ngữ cảnh** cho chính sách Zero Trust. Nó có thể bao gồm danh tính thiết bị, nguồn gốc enrollment, trạng thái quản lý, cấu hình bảo vệ, kết quả health/posture, bằng chứng attestation, mức độ mới của tín hiệu và liên kết giữa thiết bị với phiên truy cập.

Trong chương **Zero Trust assurance** của module SECURITY_SECURITY_ASSURANCE, mục tiêu không phải gắn nhãn thiết bị “an toàn tuyệt đối”. Mục tiêu là **xây dựng được một lập luận có bằng chứng** rằng thiết bị đã đáp ứng những tiêu chí được yêu cầu cho **một hành động trên một tài nguyên tại thời điểm đánh giá**, đồng thời chỉ rõ điều chưa biết, đường bypass, khả năng thay đổi posture và cách phát hiện/khắc phục sai lệch trong vận hành.

> **Luận điểm cốt lõi:** “Thiết bị đã được đăng ký”, “có chứng chỉ thiết bị”, “được MDM đánh dấu compliant”, “có hardware attestation” và “đủ điều kiện truy cập dữ liệu nhạy cảm ngay lúc này” là **năm tuyên bố khác nhau**. Device trust không thay thế authentication của người dùng, authorization đối với tài nguyên, bảo vệ session, least privilege hay giám sát hành vi.

## 1. Device trust là gì?

Trong ngữ cảnh Zero Trust, **device trust** là quyết định có phạm vi về việc liệu **thiết bị hoặc endpoint** có đáp ứng chính sách bảo mật đang áp dụng cho một request hay không, dựa trên các tín hiệu có thể kiểm tra và đủ độ mới.

Một số ví dụ thiết bị:

- Laptop hoặc desktop được tổ chức cấp và quản lý.
- Điện thoại/tablet cá nhân có profile quản lý giới hạn.
- Máy trạm của đối tác hoặc nhà thầu.
- Kiosk, thin client hoặc thiết bị dùng chung.
- Thiết bị IoT/OT, máy quét mã, thiết bị y tế trong môi trường chuyên biệt.
- Virtual desktop, VM, container host hoặc endpoint truy cập từ remote workspace.
- Máy tính cá nhân truy cập trình duyệt không có agent quản trị.

**Không phải mọi thiết bị đều cung cấp cùng bộ tín hiệu.** Một browser không thể mặc nhiên chứng minh trạng thái secure boot hoặc OS patch của máy vật lý; một workload server có thể dùng attestation khác với laptop người dùng. Chính sách cần phân biệt loại thiết bị và khả năng chứng minh.

### 1.1. Năm lớp khẳng định thường bị nhầm lẫn

| Khẳng định | Điều có thể hỗ trợ | Điều **chưa** chứng minh |
|---|---|---|
| **Device identified** | Có định danh được gán và xác minh theo một phương pháp | Không chứng minh phần cứng chưa bị xâm nhập |
| **Device enrolled** | Thiết bị có hồ sơ trong hệ quản lý | Không chứng minh posture hiện tại đạt |
| **Device managed** | MDM/UEM có khả năng áp cấu hình, thu tín hiệu và quản lý vòng đời | Không chứng minh agent luôn chạy hoặc mọi kiểm soát đều được enforcement |
| **Device compliant** | Các chỉ số được hệ quản lý đánh giá đạt policy tại thời điểm thu | Không chứng minh không có malware hoặc chưa bị attacker kiểm soát |
| **Attestation verified** | Bằng chứng có thể được verifier kiểm tra theo trust root/measurement được chọn | Không chứng minh mọi hành vi sau attestation đều an toàn hoặc mọi ứng dụng đều đáng tin |

**Device trust không phải thuộc tính vĩnh viễn.** Một thiết bị hợp lệ hôm qua có thể bị mất, mất quản lý, cài phần mềm độc hại, đổi owner hoặc trở nên không compliant hôm nay.

### 1.2. Tín hiệu và quyết định cần tách riêng

Một hệ thống nên tách:

1. **Signal collection:** thu tín hiệu từ device, MDM/UEM, EDR, identity provider, attestation verifier hoặc inventory.
2. **Signal validation:** xác minh nguồn gốc, integrity, freshness và binding.
3. **Policy evaluation:** so sánh với tiêu chí theo risk của resource/action.
4. **Enforcement:** áp dụng ALLOW, DENY, STEP_UP, LIMITED, QUARANTINE hoặc hành vi khác theo policy.
5. **Feedback:** ghi nhận và điều chỉnh quyết định khi signal/risk thay đổi.

Nếu ứng dụng chỉ đọc một boolean do client tự gửi là deviceTrusted=true, nó chưa có nền tảng assurance đáng tin.

## 2. Device trust đóng vai trò gì trong Zero Trust?

Zero Trust giảm phụ thuộc vào vị trí mạng như một bằng chứng tin cậy, tập trung vào **đánh giá ngữ cảnh của từng yêu cầu truy cập**. Device trust là một trong những ngữ cảnh đó, cùng với identity, credential strength, workload identity, authorization, resource sensitivity, session risk và hành vi.

Một quyết định truy cập có thể đặt những câu hỏi:

- Người dùng đã xác thực bằng cơ chế phù hợp chưa?
- Họ có quyền đọc resource cụ thể và thuộc đúng tenant không?
- Phiên hiện tại có liên kết được với thiết bị mà hệ thống đã xác minh không?
- Thiết bị có được quản lý/attested theo mức bảo đảm yêu cầu không?
- Tình trạng patch, encryption, EDR, screen lock và integrity có còn đạt chính sách không?
- Kết quả posture được đo **khi nào**, có còn đủ mới không?
- Môi trường truy cập hiện tại có rủi ro bổ sung không?
- Nếu không xác minh được thiết bị, có thể chỉ cho phép chức năng ít nhạy cảm hay phải từ chối?
- Nếu trạng thái thiết bị thay đổi giữa phiên, chính sách có reevaluate và thu hồi kịp thời không?

### 2.1. Zero Trust không có nghĩa không bao giờ cho phép BYOD

**Unmanaged** không đồng nghĩa **malicious**. Thiết bị không được tổ chức quản lý có thể vẫn đáp ứng một số use case ít nhạy cảm; ngược lại, thiết bị được quản lý vẫn có thể bị xâm nhập.

Policy có thể chia mức:

| Mức hoạt động | Ví dụ | Thiết bị không quản lý | Thiết bị managed/compliant |
|---|---|---|---|
| **Public** | Tài liệu công khai | Truy cập theo kiểm soát công khai | Truy cập tương tự |
| **Low sensitivity** | Xem nội dung học tập cá nhân đã xác thực | Có thể cho phép phiên hạn chế, không export/offline | Có thể cho phép theo quyền và context |
| **Medium sensitivity** | Đọc dashboard nội bộ | Có thể cần step-up, browser isolation hoặc VDI theo policy | Có thể cho phép nếu đủ posture và quyền |
| **High sensitivity** | Export PII, admin production, ký giao dịch | Thường phải từ chối nếu thiếu assurance yêu cầu | Chỉ cho phép khi tất cả điều kiện và authorization đạt |
| **Emergency** | Ứng phó sự cố theo break-glass | Quy trình ngoại lệ có thẩm quyền, phạm vi và giám sát | Tương tự; không mặc định bỏ qua kiểm tra |

Bảng chỉ minh họa tư duy theo rủi ro, **không phải quy định chung**. Nhiệm vụ, nền tảng, nghĩa vụ và khả năng enforcement quyết định mức nào được chấp nhận.

### 2.2. Authentication khác device trust

- **User authentication:** xác minh ai đang sử dụng phiên.
- **Device authentication:** xác minh endpoint sở hữu credential/khóa được đăng ký hoặc một identity tương ứng.
- **Device posture:** đo và đánh giá thuộc tính bảo mật của endpoint.
- **Device attestation:** xác minh bằng chứng cấu hình/trạng thái theo trust anchor và cơ chế cụ thể.
- **Business authorization:** xét principal có được thực hiện action trên resource không.
- **Session binding:** làm giảm khả năng một phiên/token được sử dụng từ thiết bị khác ngoài điều kiện chính sách.

Có thể có user authentication mạnh nhưng device posture yếu; cũng có thể có device tốt nhưng user không có quyền xem tài nguyên. **Cả hai phải được kiểm tra độc lập** ở những đường yêu cầu.

## 3. Mô hình kiến trúc tham chiếu

Một giải pháp điển hình có các thành phần:

- **Device:** laptop/phone/workstation với agent hoặc tính năng OS hỗ trợ.
- **MDM/UEM:** hệ quản trị enrollment, policy, cấu hình và compliance.
- **EDR/XDR:** cung cấp tín hiệu phát hiện và phản ứng từ endpoint; phạm vi bảo đảm cần xem cụ thể.
- **Identity provider (IdP):** xác thực user/device trong phạm vi hỗ trợ và phát token/session.
- **Attestation verifier:** xác minh evidence phần cứng/firmware/OS khi kiến trúc có sử dụng.
- **Policy Information Point (PIP):** tổng hợp và cung cấp posture/context đã được kiểm tra cho PDP.
- **Policy Decision Point (PDP):** đánh giá policy theo danh tính, device và resource/action.
- **Policy Enforcement Point (PEP):** gateway, proxy, ZTNA broker, API/service hoặc application enforcement.
- **Protected resource:** API, database, storage, application, admin plane.
- **Audit/telemetry:** lưu decision, posture evidence reference, thay đổi và sự cố.

~~~mermaid
flowchart LR
    D["Employee device"] --> AG["MDM / UEM / EDR agents"]
    D --> IDP["Identity provider"]
    AG --> PIP["Device posture PIP"]
    ATT["Attestation verifier"] --> PIP
    INV["Device inventory / lifecycle"] --> PIP
    IDP --> PDP["Policy Decision Point"]
    PIP --> PDP
    RISK["Resource & session risk"] --> PDP
    D --> PEP["ZTNA / API Policy Enforcement Point"]
    PDP --> PEP
    PEP --> APP["Business application"]
    APP --> DB[("Protected data")]
    PEP --> AUD["Decision audit / monitoring"]
    PDP --> AUD
~~~

**Chú ý luồng tin cậy:** PEP không nên lấy trạng thái compliant từ một header HTTP do client tự khai. Nó cần dữ liệu từ một nguồn đã được xác minh, qua kênh/binding phù hợp và theo policy version đang có hiệu lực.

### 3.1. Bảng trust boundary

| Ranh giới | Điều cần xác minh | Nếu thất bại có thể xảy ra |
|---|---|---|
| Device → MDM/UEM | Đúng thiết bị, agent/enrollment hợp lệ, kênh bảo vệ | Thiết bị giả hoặc tín hiệu không đáng tin |
| Device → Attestation verifier | Chứng cứ ký, nonce, freshness, device/key binding, measurement policy | Replay hoặc gắn evidence của thiết bị khác |
| MDM/EDR → PIP | Danh tính hệ cung cấp, tính toàn vẹn dữ liệu, timestamp, version | Compliant flag bị giả hoặc stale |
| PIP → PDP | Thuộc tính nguồn đáng tin, policy và error semantics | PDP dùng dữ liệu không phù hợp |
| IdP → PDP/PEP | User identity, token issuer/audience/expiry, mối liên kết device/session | Token đúng user nhưng chạy từ thiết bị khác |
| PDP → PEP | Decision integrity, policy version, TTL và target binding | Quyết định cũ/khác resource bị áp dụng sai |
| PEP → Resource | Không thể bypass enforcement; tài nguyên kiểm tra quyền nghiệp vụ | Thiết bị bị đánh giá tốt nhưng vẫn truy cập chéo tenant |
| Admin → Device management | Admin được cấp quyền phù hợp, thao tác được audit | Attacker đổi compliance rule thành permissive |

### 3.2. Mọi đường tới tài nguyên đều cần review

Một API dùng ZTNA gateway vẫn có thể có:

- Endpoint riêng trên mạng nội bộ.
- VPN legacy.
- API admin hoặc support console.
- Direct database/storage access.
- Service-to-service calls.
- Export/download hoặc signed URL.
- Batch/ETL job xử lý dữ liệu thay người dùng.
- Browser plugin, mobile app hoặc desktop application sử dụng flow khác.

Nếu chỉ kiểm soát web UI mà đường API khác bỏ qua điều kiện device, claim device trust chưa được chứng minh end-to-end.

## 4. Danh tính thiết bị và enrollment

### 4.1. Device identifier không tự chứng minh nguồn gốc

Thiết bị có thể có serial number, asset ID, MDM enrollment ID, certificate subject, key identifier hoặc OS installation identifier. Một chuỗi ID do client tự báo có thể bị sao chép/spoof.

**Device identity đủ tin cậy** phụ thuộc cách sinh, phân phối và chứng minh quyền sở hữu credential liên quan. Ví dụ, một certificate gắn với private key được bảo vệ trong TPM/secure hardware có thể giảm rủi ro sao chép key nếu các điều kiện được thỏa mãn. Nhưng:

- Certificate có thể được cấp sai chủ thể.
- Khóa có thể bị dùng trái phép trên chính thiết bị đã bị chiếm.
- Một certificate có thể chỉ chứng minh possession of key, không chứng minh OS compliant.
- Một khóa exportable hoặc bị backup ngoài kiểm soát có thể bị sao chép.
- Danh tính thiết bị bị thay owner hoặc mất quản lý cần được revoke.

### 4.2. Secure enrollment

Một quy trình enrollment nên:

1. Kiểm tra danh tính của người/đơn vị được phép đăng ký thiết bị.
2. Xác minh asset ownership và loại thiết bị theo chính sách.
3. Thiết lập kênh được bảo vệ tới hệ quản trị.
4. Cấp device identity hoặc certificate qua quy trình được kiểm soát.
5. Khi có phần cứng hỗ trợ, tạo khóa thiết bị trong vùng bảo vệ theo policy.
6. Cài cấu hình và agent cần thiết; áp policy ngay khi đăng ký.
7. Chạy posture/attestation baseline.
8. Chỉ đánh dấu eligible cho các resource tương ứng sau khi đạt kiểm tra.
9. Ghi owner, enrollment time, key/certificate reference, policy version và bằng chứng.
10. Có đường xử lý enrollment thất bại, chuyển chủ hoặc decommission.

**Enrollment token không nên là credential tái sử dụng vô hạn**, đặc biệt nếu ai lấy được token có thể tự đăng ký máy lạ như thiết bị công ty.

### 4.3. Vòng đời device identity

~~~mermaid
flowchart TD
    A["Asset onboarding / ownership check"] --> B["Enrollment & device identity"]
    B --> C["Baseline + attestation / posture"]
    C --> D{"Meets policy?"}
    D -- "No / unknown" --> Q["LIMITED / QUARANTINE / DENY"]
    D -- "Yes for resource tier" --> E["Access eligible, not automatically authorized"]
    E --> F["Continuous signal refresh"]
    F --> G{"Lost / stale / compromised / offboarded?"}
    G -- "No" --> E
    G -- "Yes" --> H["Restrict session, revoke identity and remediate"]
    H --> I["Re-enroll or decommission"]
    I --> C
    Q --> J["Fix posture / obtain new evidence"]
    J --> C
~~~

Offboarding cần thu hồi certificate, enrollment, MDM authority, token/session binding và mọi grant liên quan. Xóa thiết bị khỏi inventory mà certificate còn dùng được có thể tạo đường truy cập ngoài kiểm soát.

## 5. Các loại tín hiệu device posture

**Posture** là tập thuộc tính mô tả trạng thái endpoint có liên quan tới rủi ro. Chúng có thể đến từ OS, security agent, MDM, firmware hoặc attestation. Không nên gộp mọi thứ thành một cờ không rõ nguồn.

| Tín hiệu | Điều có thể chứng minh theo cơ chế | Giới hạn thường gặp |
|---|---|---|
| **Management enrollment** | Thiết bị hiện có hồ sơ/cấu hình quản lý | Enrollment không bảo đảm agent liên lạc hoặc chính sách đang áp dụng |
| **OS version/patch level** | Version/patch được agent hoặc hệ quản lý báo cáo | Reporting trễ, cấu hình vendor, zero-day vẫn tồn tại |
| **Disk encryption** | Thuộc tính mã hóa ổ đĩa và chính sách key recovery theo nguồn | Không chứng minh dữ liệu plaintext không tồn tại trong app/session |
| **Secure boot / measured boot** | Một số bằng chứng về chain boot/measurements khi hỗ trợ | Không chứng minh runtime không bị xâm nhập sau boot |
| **EDR/AV health** | Agent hoạt động, update và một số detection/risk state | Agent có thể bị vô hiệu hóa/bypass, detection không hoàn hảo |
| **Firewall/configuration** | Cấu hình bảo vệ host theo policy | Không bảo vệ mọi network/application path |
| **Screen lock** | Thiết lập/hiệu lực cơ chế khóa màn hình | Không ngăn session theft hoặc remote compromise |
| **App integrity** | Một số kiểm tra ứng dụng hoặc môi trường chạy | Không tự chứng minh API caller được quyền trên dữ liệu |
| **Root/jailbreak detection** | Chỉ báo thay đổi quyền hệ thống ngoài policy | Có false positive/false negative và khả năng bypass |
| **Hardware-backed key** | Khóa có thể được tạo/giữ trong vùng phần cứng với thuộc tính cụ thể | Không đồng nghĩa chứng minh mọi process trên thiết bị đáng tin |
| **Certificate status** | Credential được phát hành và chưa bị revoke theo nguồn đã kiểm | Không tự bao phủ patch/compliance/owner |
| **Risk signal** | EDR/SOC thấy hành vi bất thường hoặc incident | Không thấy alert không đồng nghĩa an toàn |
| **Time/freshness** | Bằng chứng được thu gần thời điểm quyết định | Timestamp có thể không tin cậy nếu nguồn/binding yếu |

### 5.1. Hệ quản lý báo compliant có nghĩa gì?

Một MDM/UEM có thể kết luận **compliant** khi các thuộc tính cấu hình do policy định nghĩa được đáp ứng. Điều này hỗ trợ quyết định nhưng cần xác định:

- Policy và version nào?
- Các thiết bị nào được kiểm tra?
- Field nào được đo thực tế và field nào chỉ dựa báo cáo?
- Last check-in lúc nào?
- Có tín hiệu EDR/incident nào mâu thuẫn không?
- Policy có bị tắt hoặc exception không?
- Trạng thái compliant áp dụng cho device, user session hay application container?
- Điều gì xảy ra nếu device offline quá lâu?

Đừng gắn nhãn **trusted=true** chỉ vì management system trả một trạng thái không kèm policy version và freshness.

### 5.2. Tính độc lập của tín hiệu

Ba thuộc tính cùng lấy từ một agent bị chiếm không phải ba nguồn bằng chứng độc lập. Ngược lại, attestation hardware, MDM management status và EDR threat signal có thể tăng khả năng đối chiếu, nhưng vẫn có phụ thuộc chung như OS, IdP và chính sách quản trị.

Assurance case cần ghi **nguồn và các phụ thuộc**, không đếm số lượng cờ xanh làm thước đo tin cậy tuyệt đối.

## 6. Device attestation và điều có thể chứng minh

**Attestation** là việc một thành phần cung cấp bằng chứng về danh tính, cấu hình hoặc trạng thái theo một cơ chế và trust anchor mà verifier có thể xác minh.

Ví dụ trong môi trường có TPM:

- Thiết bị có thể có những khóa/phép toán gắn với phần cứng.
- Chuỗi boot có thể tạo measurements liên quan tới firmware/boot components.
- Attester tạo evidence về measurements hoặc claims.
- Verifier kiểm chữ ký, nonce, trust anchor và so sánh evidence với reference values/policy.
- Kết quả là **một attestation appraisal** có scope, timestamp và điều kiện, không phải kết luận mọi phần mềm đều sạch.

### 6.1. Attestation flow ở mức nguyên lý

~~~mermaid
sequenceDiagram
    participant C as Client device
    participant V as Attestation verifier
    participant P as Policy decision point
    participant A as Protected application
    C->>V: Xin challenge / nonce
    V-->>C: Nonce và yêu cầu evidence
    C->>V: Signed evidence / claims / device-key proof
    V->>V: Verify chain, signature, nonce, reference values
    V-->>P: Appraisal + device binding + timestamp
    C->>A: Request đã xác thực user/session
    A->>P: Authorization + resource + device context
    P-->>A: Decision theo risk và freshness
    A-->>C: Allowed / limited / denied
~~~

Sơ đồ **không khẳng định một loại thiết bị/OS cụ thể thực hiện đủ mọi bước**. Các nền tảng có cơ chế attestation khác nhau và có thể không hỗ trợ điều kiện cần thiết.

### 6.2. Nonce, replay và binding

Một attestation verifier cần xem:

- Evidence có được ký/xác thực từ trust root được chấp nhận không?
- Challenge/nonce có mới và gắn với phiên kiểm tra không?
- Measurement claims có đầy đủ và nằm trong phạm vi được kiểm không?
- Evidence có thể bị gửi lại từ một thiết bị khác không?
- Key/certificate/nonce có gắn với đúng device identity không?
- Device evidence có được gắn với **session hoặc token truy cập** theo cơ chế đáng tin không?
- Reference values/policy version có đúng thiết bị và môi trường không?
- Đồng hồ, freshness và khả năng phân biệt kết quả UNKNOWN/FAIL được quản lý ra sao?

Nếu attacker lấy evidence tốt từ thiết bị A rồi dùng cho session trên thiết bị B, hệ thống vẫn có thể bị đánh lừa nếu không có **cryptographic binding** phù hợp.

### 6.3. TPM, secure boot và measured boot

- **Secure boot** có thể ngăn một số boot components không được phép chạy theo policy trust.
- **Measured boot** ghi nhận measurements về boot chain theo cơ chế nền tảng; verifier cần policy/reference values để đánh giá.
- **TPM** có thể hỗ trợ lưu khóa/attestation measurements và các thao tác liên quan.
- **Hardware-backed key** có thể hỗ trợ bảo vệ private key và chứng minh possession.

Một pass của measured boot có thể hỗ trợ claim rằng một số trạng thái boot phù hợp. Nó **không chứng minh runtime luôn sạch, không có ứng dụng độc hại, không có session hijack và người dùng không bị phishing**.

### 6.4. Mobile device attestation

Điện thoại có thể hỗ trợ cơ chế attestation của hệ điều hành hoặc secure hardware. Tuy nhiên:

- Khả năng chứng minh device identity/app integrity khác nhau giữa nền tảng và phiên bản.
- Một số mechanism chứng minh đặc tính **ứng dụng**, không phải toàn bộ device posture.
- App trên máy rooted/jailbroken có thể cố giả mạo hoặc vượt kiểm tra cục bộ.
- Device check chỉ ở lần đăng nhập có thể mất giá trị khi hệ thống thay đổi.
- Không nên lưu trữ device fingerprint dài hạn vượt nhu cầu nếu không có mục đích/căn cứ phù hợp.

Cần đánh giá giới hạn của cơ chế cụ thể trước khi xây policy “attested = trusted”.

## 7. MDM, UEM, EDR và trách nhiệm của chúng

### 7.1. MDM/UEM

MDM/UEM thường hỗ trợ:

- Enrollment và asset ownership.
- Triển khai cấu hình OS và profile.
- Chính sách patch/encryption/passcode.
- Certificate/credential lifecycle ở mức hỗ trợ.
- Compliance reporting và remote management.
- Wipe/retire trong phạm vi quyền quản lý.
- Điều phối trạng thái thiết bị cho conditional access.

Khi tổ chức dùng BYOD, UEM có thể quản lý một **work profile/app container** thay vì toàn bộ thiết bị. Điều này ảnh hưởng loại thông tin và hành động quản lý có thể áp dụng. Không mặc định admin có toàn quyền trên thiết bị cá nhân.

### 7.2. EDR/XDR

EDR có thể cung cấp:

- Agent health và version.
- Một số detection/incident risk indicators.
- Device isolation/quarantine theo khả năng.
- Telemetry phục vụ điều tra.
- Signal về threat posture để tăng hoặc hạn chế quyền truy cập.

EDR không thay thế MDM, cũng không chứng minh vắng malware chỉ vì không có alert. Cần xem **agent tamper protection, heartbeat freshness, coverage, signal delay và xử lý false positive**.

### 7.3. Nguyên tắc tích hợp posture

- Không tin client-controlled header/device status.
- Bảo vệ API và credential giữa MDM/EDR với PIP.
- Lưu source, timestamp, policy version, device key và state.
- Phân biệt COMPLIANT/NON_COMPLIANT/UNKNOWN/OFFLINE/REVOKED.
- Định nghĩa conflict resolution: EDR high-risk có ưu tiên hơn MDM compliant không?
- Có cơ chế reconcile khi thiết bị đổi owner/OS reinstall/re-enroll.
- Audit thay đổi compliance policy và admin overrides.
- Có cơ chế cảnh báo khi feed bị ngắt hoặc dữ liệu bị stale.

## 8. Managed, unmanaged, BYOD, contractor và kiosk

### 8.1. Managed corporate device

Thường có asset inventory, MDM/UEM, certificate, patch policy, EDR và khả năng remote revoke. Đây có thể là nền tảng cho assurance cao hơn, nhưng không loại bỏ rủi ro ứng dụng, user identity và session.

### 8.2. BYOD

Có thể áp mô hình:

- Browser access tới dữ liệu ít nhạy cảm.
- Managed work profile/container trên mobile.
- Application-level protection.
- Remote browser isolation/VDI.
- Download/export restrictions.
- Short sessions và step-up authentication.

**Không nên thu thập quá mức dữ liệu cá nhân của người sở hữu BYOD** chỉ để áp security control. Cần thông báo rõ loại telemetry, giới hạn quyền quản lý và dữ liệu nào bị xóa khi offboarding.

### 8.3. Unmanaged contractor device

Nhà thầu có thể dùng máy không thuộc hệ quản lý. Policy có thể chọn **limited browser access, VDI hoặc thiết bị được cấp tạm** cho tài nguyên nhạy cảm. Hợp đồng không tự chứng minh posture; cần một phương án để kiểm chứng hoặc giới hạn.

### 8.4. Shared kiosk

Kiosk có thể có device identity mạnh nhưng không gắn với một người dùng duy nhất. Cần session isolation, logout/cleanup, screen privacy, local storage controls và user authentication. Không dùng “device compliant” làm lý do bỏ kiểm tra user.

### 8.5. IoT/OT

Thiết bị chuyên dụng có thể không hỗ trợ MDM/EDR phổ thông hoặc không thể cập nhật thường xuyên do yêu cầu availability. Có thể cần device identity, network microsegmentation, allowlisted protocols, monitoring và compensating controls. Không gán COMPLIANT bằng cách giả lập tín hiệu OS chưa có; policy cần một profile assurance riêng cho loại thiết bị.

## 9. Session và token: device trust có được gắn với request không?

Một vấn đề phổ biến: user đăng nhập trên laptop managed, IdP xác nhận device compliant và phát bearer token. Nếu token bị đánh cắp, nó có thể được sử dụng từ một máy khác nếu hệ thống không có cơ chế sender constraint hoặc phát hiện rủi ro phù hợp.

Cần phân biệt:

- **Device registration:** có record của thiết bị.
- **Device proof-of-possession:** thiết bị hoặc client chứng minh sở hữu credential.
- **Session binding:** phiên/token được ràng buộc với khóa hoặc context đáng tin.
- **Continuous posture:** trạng thái thiết bị tiếp tục được xem xét sau khi phát token.
- **Business authorization:** user/subject vẫn phải có quyền trên resource.

### 9.1. Sender-constrained tokens và mTLS/DPoP

Tùy nền tảng, cơ chế như **mTLS-bound access token** hoặc **DPoP** có thể giúp hạn chế việc replay access token trên một client không sở hữu khóa tương ứng. Nhưng:

- Nó **không tự chứng minh thiết bị đạt OS posture**.
- Nếu attacker kiểm soát chính client hoặc khóa ký, vẫn có thể lạm dụng token.
- Browser, native app và gateway có mức hỗ trợ/binding khác nhau.
- Token issuer, audience, scope, expiry, key binding và server-side verification phải được kiểm tra.
- Device identity và key material có thể bị thay đổi giữa các phiên, cần lifecycle và revocation.

Không viết claim “DPoP chứng minh thiết bị an toàn” hoặc “mTLS đồng nghĩa MDM compliant”.

### 9.2. TOCTOU và session lifetime

**Time-of-check/time-of-use** xảy ra khi posture đã đạt tại thời điểm T1 nhưng thiết bị thay đổi trước T2 mà hệ thống vẫn dùng kết quả cũ.

Cần xác định:

1. Lúc nào device posture được kiểm tra?
2. Bao lâu kết quả còn hợp lệ theo risk tier?
3. Có signal push khi EDR phát hiện nguy cơ hoặc MDM mất heartbeat không?
4. Khi user chuyển thiết bị, token/cookie có còn được chấp nhận không?
5. Policy có reevaluate khi thực hiện action nhạy cảm như export/admin không?
6. Khi posture UNKNOWN vì hệ thống quản lý lỗi, PEP có hành vi nào?
7. Có thể chấm dứt session/ủy quyền đã cấp trong thời gian chấp nhận được không?

Một số hệ thống chỉ có thể giảm rủi ro qua **token lifetime ngắn, reauthentication và refresh checks**, không thể revoke tức thời mọi token. Assurance phải ghi giới hạn thực tế.

## 10. Chính sách device trust theo mức rủi ro tài nguyên

Thay vì một cờ toàn hệ thống, có thể định nghĩa **resource tiers** và tiêu chí thiết bị.

| Resource tier | Yêu cầu minh họa | Khi tín hiệu thiếu hoặc lỗi |
|---|---|---|
| **Public** | Không dùng device trust như điều kiện truy cập; vẫn có abuse protection | Phục vụ theo chính sách public |
| **Low** | User authenticated, quyền tài nguyên hợp lệ | Có thể giới hạn tính năng/tải dữ liệu nếu thiết bị chưa xác minh |
| **Medium** | Managed hoặc containerized access, posture mới và các chính sách thích hợp | STEP_UP, LIMITED/VDI hoặc DENY theo risk |
| **High** | Managed, identity/session binding, compliant posture, kiểm tra threat signal; attestation nếu bắt buộc | DENY cho hành động nhạy cảm khi chưa đủ evidence |
| **Critical admin** | High controls + privileged session, MFA/approval và continuous monitoring | Fail-safe, emergency workflow có thẩm quyền nếu cần |

Đây là **policy profile minh họa**. Không có khoảng freshness 5 hoặc 10 phút nào tự động là chuẩn cho tất cả hoạt động. Tổ chức cần xác định từ **threat model, risk tolerance, khả năng signal và mức độ ảnh hưởng**.

### 10.1. Các kết quả access cần phân biệt

| Kết quả | Diễn giải | Điều không được làm |
|---|---|---|
| **ALLOW_FULL** | Đạt điều kiện device cho tập action đã định, đồng thời có authorization độc lập | Không suy rộng thành quyền admin hoặc mọi resource |
| **ALLOW_LIMITED** | Chỉ truy cập phần ít nhạy cảm hoặc qua môi trường bị giới hạn | Không hiểu là cho phép export/admin |
| **STEP_UP** | Cần thêm user authentication, device verification hoặc approval | Không tự coi step-up là device compliant |
| **QUARANTINE** | Chỉ cho phép remediation/update/check-in theo policy | Không để quarantine route truy cập dữ liệu production |
| **DENY** | Không đạt điều kiện hoặc có tín hiệu rủi ro bị cấm | Không tự fallback sang đường VPN legacy |
| **REVIEW_REQUIRED** | Dữ liệu chưa đầy đủ hoặc bị mâu thuẫn | Không chuyển UNKNOWN thành ALLOW do lỗi code |

### 10.2. Freshness phải tính theo nguồn tin cậy

Ví dụ posture có timestamp do MDM ký/xác nhận. PDP phải có cách đánh giá độ mới của signal dựa trên thời gian đáng tin và policy version, không lấy chuỗi timestamp do client tự khai.

Với resource nhạy cảm, posture stale có thể dẫn đến DENY; với use case ít nhạy cảm, LIMITED/step-up có thể hợp lý. Điều này phải **được quy định trước**, không viết exception fail-open khi production có lỗi.

### 10.3. Xung đột tín hiệu

Ví dụ MDM báo compliant, nhưng EDR báo thiết bị đang bị cô lập. Một policy tốt không nên chọn trạng thái tốt nhất bằng toán OR. Cần precedence theo risk: tín hiệu compromise hoặc REVOKED từ nguồn có thẩm quyền có thể chặn truy cập bất chấp MDM compliance.

Tương tự, attestation pass về boot state không tự ghi đè kết quả malware detection ở runtime. **Các tín hiệu mô tả những thuộc tính khác nhau.**

## 11. Threat modeling Device trust

| Threat / misuse | Kịch bản | Hậu quả | Control cần đánh giá |
|---|---|---|---|
| **Spoofed device ID** | Client tự gửi ID của laptop công ty | Bypass device policy | Identity credential, mTLS/PoP, source verification |
| **Stolen bearer token** | Token lấy trên device managed được dùng từ host khác | Truy cập trái phép | Sender constraint, short TTL, risk detection |
| **Stale compliance** | MDM không nhận heartbeat nhưng vẫn báo trusted | Device lỗi thời được phép truy cập | Freshness limit, UNKNOWN handling |
| **Attestation replay** | Evidence cũ từ device A dùng trên B | Giả tín hiệu attested | Nonce, binding, verifier policy |
| **Compromised agent** | Endpoint giả EDR healthy | Sai posture | Independent signals, tamper protection, monitoring |
| **Management account compromise** | Attacker sửa compliance rule | Quyền rộng cấp hàng loạt | PAM/SoD/change control/audit |
| **Certificate misuse** | Credential device không bị revoke khi máy mất | Thiết bị khác hoặc attacker vẫn dùng được | Key lifecycle, loss response, session revoke |
| **PEP bypass** | API direct/VPN legacy không kiểm tra device | Truy cập bất chấp PDP | Access-path inventory và layered enforcement |
| **Cross-tenant access** | Device compliant nhưng principal đọc tenant khác | Lộ dữ liệu | Resource authorization độc lập |
| **False quarantine** | Signal lỗi khiến nhiều máy bị chặn | Availability/operational harm | Safe degraded modes, retry, appeal process |
| **Overcollection** | Device monitoring thu dữ liệu riêng tư quá mức | Privacy harm | Purpose limitation, minimization và access controls |
| **Offline grace abuse** | Thiết bị không check-in vẫn có grace dài vô hạn | Thiết bị không còn được kiểm soát | Risk-based offline windows và expiry |
| **TOCTOU** | Device đạt posture khi login nhưng mất sau đó | Session tiếp tục bất chấp rủi ro | Re-evaluation, token/session controls |
| **Supply-chain compromise** | Agent/firmware policy hoặc update bị thay | Attestation/compliance kém tin cậy | Provenance, change control, verification |

### 11.1. Không coi mọi False Positive là vô hại

Một chính sách deny mọi trường hợp UNKNOWN có thể bảo vệ confidentiality nhưng làm gián đoạn cứu hộ, vận hành y tế hoặc phản ứng sự cố. Chính sách phải cân nhắc **confidentiality, integrity, availability và khả năng khôi phục**, có phương án remediation/exception được giám sát, không bỏ qua bảo mật khi gặp lỗi.

## 12. Vòng đời phát hiện và khắc phục thiết bị không compliant

Một thiết bị mất compliance không nhất thiết phải bị xóa dữ liệu hoặc cô lập toàn bộ ngay trong mọi tình huống. Cần playbook theo severity:

1. Nhận sự kiện NON_COMPLIANT, REVOKED, LOST, COMPROMISED hoặc UNKNOWN từ nguồn đáng tin.
2. Xác minh device identity, signal và timestamp.
3. Xác định resources/sessions đang được thiết bị sử dụng.
4. Áp policy: DENY, LIMITED, STEP_UP hoặc QUARANTINE theo risk.
5. Thu hồi hoặc giảm quyền phiên/credential trong khả năng kiến trúc.
6. Gửi hướng dẫn remediation: update, encryption, agent repair hoặc kiểm tra bảo mật.
7. Tránh tiết lộ dữ liệu nhạy cảm trong thông báo lỗi/hướng dẫn.
8. Re-check posture sau remediation; không tin trạng thái tự khai.
9. Ghi audit và bằng chứng re-enable; review incident nếu có khả năng compromise.
10. Nếu device bị mất/đổi chủ, thực hiện revocation và decommission phù hợp.

### 12.1. Quarantine phải là vùng có quyền giới hạn

Một device trong quarantine có thể cần truy cập hệ update/MDM/help desk. Nhưng **không nên được quyền gọi cùng API dữ liệu production** chỉ vì network route vẫn còn.

Quarantine controls cần test cả:
- Allowed remediation destinations.
- Blocked sensitive resources.
- Không có direct path qua VPN/CDN/API cũ.
- Không tự thoát quarantine khi agent ngừng gửi tín hiệu.
- Thời hạn/owner cho ngoại lệ và hồi phục.

### 12.2. Offboarding hoặc mất thiết bị

Một máy đã mất không chỉ là vấn đề compliance; có thể cần:

- Mark LOST/REVOKED trong inventory.
- Vô hiệu device certificate/key references theo quy trình hỗ trợ.
- Revoke user sessions/token và refresh credentials khi cần.
- Review truy cập gần nhất và các dữ liệu đã sync/offline.
- Phân loại incident hoặc privacy impact nếu có dữ liệu nhạy cảm.
- Remote wipe khi có khả năng và thẩm quyền, nhưng không giả định wipe đã thành công nếu thiết bị offline.
- Chỉ đóng xử lý khi evidence/giới hạn còn lại được ghi rõ.

## 13. Device trust là một phần của defense in depth

Tài nguyên nhạy cảm không nên chỉ có một lớp “compliant device = ALLOW”.

### 13.1. Các lớp bảo vệ bổ trợ

| Lớp | Vai trò | Bằng chứng |
|---|---|---|
| **Identity** | Xác thực user/workload | IdP/token verification, authentication logs |
| **Device** | Đánh giá binding, management, posture, attestation | MDM/EDR/attestation result, freshness |
| **Session** | Điều kiện liên tục và khả năng giảm/revoke | Token policy, session management tests |
| **Authorization** | Subject được phép action trên resource cụ thể | RBAC/ABAC/ReBAC, tenant isolation tests |
| **Application** | Business approval, validation và misuse prevention | Negative operation tests |
| **Data** | Encryption, minimization, download/export controls | Config, access controls, DLP/rights tests |
| **Network** | Giới hạn đường truy cập và lateral movement | Segmentation/PEP bypass tests |
| **Operations** | Incident, monitoring, patch, key/device lifecycle | Audit, runbooks, response exercises |

Một thiết bị “trusted” có thể là một yếu tố hỗ trợ quyền truy cập, nhưng không phải **giấy thông hành toàn hệ thống**. Khi risk signal tăng, mức quyền có thể giảm ngay cả với device managed.

### 13.2. Nguyên tắc least privilege theo thiết bị

Một thiết bị unmanaged vẫn có thể xem một bản thông tin đã hạn chế nếu policy cho phép, nhưng không được suy ra quyền export hàng loạt. Một thiết bị managed/compliant cũng chỉ được thực hiện hành động mà **principal và resource policy** cho phép.

Vì vậy, **device trust là điều kiện bổ sung, không cấp quyền nghiệp vụ**.

## 14. Device trust và quyền riêng tư

Thu thập posture có thể tạo thêm dữ liệu cá nhân về thiết bị và người dùng. Những tín hiệu như danh sách ứng dụng, vị trí, mạng, ID phần cứng hoặc behavioral telemetry có thể nhạy cảm.

PIA/privacy review cần hỏi:

- Mục đích của từng field device telemetry là gì?
- Có thể chỉ thu kết luận đạt/không đạt cho một policy thay vì danh sách đầy đủ các ứng dụng không?
- Có cần theo dõi vị trí chính xác không?
- Ai truy cập được raw posture và trong bao lâu?
- Nhân viên/BYOD owner được thông tin về phạm vi quản lý và thu thập như thế nào?
- Có tách dữ liệu security assessment khỏi mục đích giám sát năng suất hay quảng cáo không?
- Có thể dùng pseudonymous references và controlled lookup thay vì device fingerprint dùng chung mọi dịch vụ không?
- Khi thiết bị mất quản lý hoặc nhân viên rời công ty, telemetry được lưu/xóa theo schedule nào?
- Cơ chế appeal/remediation có tránh bất lợi không cần thiết do False Positive không?

**Zero Trust không phải yêu cầu thu thập mọi dữ liệu có thể lấy được từ thiết bị.** Privacy-aware telemetry nên đủ để ra quyết định có bằng chứng nhưng giới hạn thu thập, chia sẻ và lưu trữ theo mục đích.


## 15. Java 17: policy device trust theo risk và dữ liệu đã xác minh

Ví dụ sau minh họa một lớp **policy decision** thuần Java, không tương tác trực tiếp với MDM, IdP hoặc TPM. Nó chỉ nhận **VerifiedDeviceAccess** đã được lắp ghép từ nguồn tin cậy ở server-side. Không truyền object này nguyên vẹn từ JSON client.

Trong ví dụ giả định:

- **HIGH** là thao tác nhạy cảm như export dữ liệu khách hàng hoặc admin.
- **LOW** là thao tác ít nhạy cảm đã được application authorization phê duyệt.
- Device **REVOKED** hoặc **NON_COMPLIANT** bị từ chối theo chính sách minh họa.
- Resource **HIGH** chỉ được ALLOW_FULL khi có liên kết device–session, quản lý, compliant posture, attestation và bằng chứng đủ mới.
- Resource **LOW** có thể ALLOW_LIMITED khi chưa chứng minh đủ posture nhưng principal đã authenticated/authorized và không có tín hiệu phủ quyết. LIMITED phải được PEP ánh xạ tới **tập action/dữ liệu bị giới hạn**, không được hiểu là một dạng full access.
- Mốc posture age tối đa **10 phút** và dung sai đồng hồ **30 giây** chỉ là số để minh họa cách kiểm tra, không phải chuẩn Zero Trust bắt buộc.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

enum DeviceManagement {
    MANAGED, UNMANAGED, UNKNOWN
}

enum DevicePosture {
    COMPLIANT, NON_COMPLIANT, UNKNOWN
}

enum ResourceRisk {
    LOW, HIGH
}

enum DeviceDecision {
    ALLOW_FULL, ALLOW_LIMITED, DENY, REVIEW_REQUIRED
}

record VerifiedDeviceAccess(
        String subjectId,
        String subjectTenant,
        String resourceTenant,
        boolean userAuthenticated,
        boolean resourceAuthorized,
        String deviceId,
        String sessionBoundDeviceId,
        DeviceManagement management,
        DevicePosture posture,
        boolean attestationVerified,
        boolean deviceRevoked,
        Instant postureObservedAt,
        ResourceRisk resourceRisk) {}

final class DeviceTrustPolicy {
    private static final Duration MAX_POSTURE_AGE =
            Duration.ofMinutes(10);
    private static final Duration CLOCK_SKEW =
            Duration.ofSeconds(30);

    private DeviceTrustPolicy() {}

    static DeviceDecision evaluate(
            VerifiedDeviceAccess access,
            Instant now) {

        if (access == null || now == null
                || access.resourceRisk() == null
                || access.management() == null
                || access.posture() == null
                || access.subjectId() == null
                || access.subjectId().isBlank()
                || access.subjectTenant() == null
                || access.subjectTenant().isBlank()
                || access.resourceTenant() == null
                || access.resourceTenant().isBlank()) {
            return DeviceDecision.REVIEW_REQUIRED;
        }

        // Device posture cannot grant business authorization.
        if (!access.userAuthenticated()
                || !access.resourceAuthorized()
                || !Objects.equals(
                    access.subjectTenant(),
                    access.resourceTenant())) {
            return DeviceDecision.DENY;
        }

        // A confirmed revocation or failed posture overrides
        // a previously passing compliance assessment.
        if (access.deviceRevoked()
                || access.posture()
                        == DevicePosture.NON_COMPLIANT) {
            return DeviceDecision.DENY;
        }

        boolean hasDeviceProof =
                access.deviceId() != null
                && !access.deviceId().isBlank()
                && access.sessionBoundDeviceId() != null
                && !access.sessionBoundDeviceId().isBlank();

        // If both identities are present, mismatch is suspicious.
        if (hasDeviceProof && !Objects.equals(
                access.deviceId(),
                access.sessionBoundDeviceId())) {
            return DeviceDecision.DENY;
        }

        boolean postureFresh =
                access.postureObservedAt() != null
                && !access.postureObservedAt()
                        .isAfter(now.plus(CLOCK_SKEW))
                && !access.postureObservedAt()
                        .isBefore(now.minus(MAX_POSTURE_AGE));

        boolean satisfiesHighAssurance =
                hasDeviceProof
                && postureFresh
                && access.management() == DeviceManagement.MANAGED
                && access.posture() == DevicePosture.COMPLIANT
                && access.attestationVerified();

        if (access.resourceRisk() == ResourceRisk.HIGH) {
            return satisfiesHighAssurance
                    ? DeviceDecision.ALLOW_FULL
                    : DeviceDecision.DENY;
        }

        return satisfiesHighAssurance
                ? DeviceDecision.ALLOW_FULL
                : DeviceDecision.ALLOW_LIMITED;
    }
}
~~~

### 15.1. Ranh giới của ví dụ

Hàm trên **không thực hiện xác thực hoặc remote attestation**. Một số điều kiện tiên quyết phải do các thành phần khác bảo đảm:

- **subjectId, userAuthenticated:** lấy từ IdP/verified authentication context.
- **resourceAuthorized:** kết quả của resource-level authorization trên action cụ thể, không phải cờ do client tự gửi.
- **subjectTenant/resourceTenant:** truy xuất từ nguồn authoritative và record ownership.
- **deviceId/sessionBoundDeviceId:** đến từ cơ chế device proof-of-possession/session binding được kiểm chứng bằng mật mã; chỉ so sánh hai chuỗi do client gửi **không đủ**.
- **management/posture:** từ MDM/UEM/EDR đã được xác minh nguồn, policy version và freshness.
- **attestationVerified:** kết quả appraised của verifier đáng tin cho scope yêu cầu, không phải chỉ kiểm tra signature bất kỳ.
- **deviceRevoked:** trạng thái có thẩm quyền từ registry/revocation feed; cần cập nhật kịp thời.
- **resourceRisk:** từ resource catalogue hoặc policy của tổ chức, không để caller tự hạ HIGH thành LOW.
- **now:** lấy từ clock phía server đã được kiểm soát, không dùng timestamp thiết bị tự khai.

Để tránh kết luận sai, **ALLOW_FULL trong hàm chỉ là đạt điều kiện device trust của ví dụ**, không được tự suy ra quyền thực hiện mọi hành động. PEP vẫn phải kết hợp business authorization, scope và các controls khác. Tương tự, **ALLOW_LIMITED** chỉ có ý nghĩa nếu có danh sách action và data classes bị hạn chế được thực thi rõ ràng.

### 15.2. JUnit 5: kiểm thử các đường cấp quyền và fail-safe

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class DeviceTrustPolicyTest {
    private static final Instant NOW =
            Instant.parse("2026-11-28T00:00:00Z");

    private static VerifiedDeviceAccess full(ResourceRisk risk) {
        return new VerifiedDeviceAccess(
                "user-42", "tenant-A", "tenant-A",
                true, true,
                "device-100", "device-100",
                DeviceManagement.MANAGED,
                DevicePosture.COMPLIANT,
                true, false, NOW.minusSeconds(30), risk);
    }

    @Test
    void permitsHighRiskOnlyWithFreshTrustedContext() {
        assertEquals(DeviceDecision.ALLOW_FULL,
                DeviceTrustPolicy.evaluate(
                        full(ResourceRisk.HIGH), NOW));
    }

    @Test
    void deniesHighRiskOnStalePosture() {
        var stale = new VerifiedDeviceAccess(
                "user-42", "tenant-A", "tenant-A",
                true, true, "device-100", "device-100",
                DeviceManagement.MANAGED,
                DevicePosture.COMPLIANT,
                true, false, NOW.minusSeconds(3600),
                ResourceRisk.HIGH);
        assertEquals(DeviceDecision.DENY,
                DeviceTrustPolicy.evaluate(stale, NOW));
    }

    @Test
    void deniesHighRiskOnUnmanagedDevice() {
        var unmanaged = new VerifiedDeviceAccess(
                "user-42", "tenant-A", "tenant-A",
                true, true, "device-100", "device-100",
                DeviceManagement.UNMANAGED,
                DevicePosture.UNKNOWN,
                false, false, NOW,
                ResourceRisk.HIGH);
        assertEquals(DeviceDecision.DENY,
                DeviceTrustPolicy.evaluate(unmanaged, NOW));
    }

    @Test
    void limitsLowRiskWhenDeviceIsNotVerified() {
        var limited = new VerifiedDeviceAccess(
                "user-42", "tenant-A", "tenant-A",
                true, true, null, null,
                DeviceManagement.UNMANAGED,
                DevicePosture.UNKNOWN,
                false, false, null,
                ResourceRisk.LOW);
        assertEquals(DeviceDecision.ALLOW_LIMITED,
                DeviceTrustPolicy.evaluate(limited, NOW));
    }

    @Test
    void deniesConfirmedNonCompliantDevice() {
        var unhealthy = new VerifiedDeviceAccess(
                "user-42", "tenant-A", "tenant-A",
                true, true, "device-100", "device-100",
                DeviceManagement.MANAGED,
                DevicePosture.NON_COMPLIANT,
                true, false, NOW,
                ResourceRisk.LOW);
        assertEquals(DeviceDecision.DENY,
                DeviceTrustPolicy.evaluate(unhealthy, NOW));
    }

    @Test
    void deniesRevokedDevice() {
        var revoked = new VerifiedDeviceAccess(
                "user-42", "tenant-A", "tenant-A",
                true, true, "device-100", "device-100",
                DeviceManagement.MANAGED,
                DevicePosture.COMPLIANT,
                true, true, NOW,
                ResourceRisk.HIGH);
        assertEquals(DeviceDecision.DENY,
                DeviceTrustPolicy.evaluate(revoked, NOW));
    }

    @Test
    void deniesWrongDeviceBinding() {
        var swapped = new VerifiedDeviceAccess(
                "user-42", "tenant-A", "tenant-A",
                true, true, "device-100", "device-999",
                DeviceManagement.MANAGED,
                DevicePosture.COMPLIANT,
                true, false, NOW,
                ResourceRisk.HIGH);
        assertEquals(DeviceDecision.DENY,
                DeviceTrustPolicy.evaluate(swapped, NOW));
    }

    @Test
    void deniesCrossTenantEvenOnCompliantDevice() {
        var crossTenant = new VerifiedDeviceAccess(
                "user-42", "tenant-A", "tenant-B",
                true, true, "device-100", "device-100",
                DeviceManagement.MANAGED,
                DevicePosture.COMPLIANT,
                true, false, NOW,
                ResourceRisk.HIGH);
        assertEquals(DeviceDecision.DENY,
                DeviceTrustPolicy.evaluate(crossTenant, NOW));
    }

    @Test
    void deniesWhenUserIsNotAuthorized() {
        var unauthorized = new VerifiedDeviceAccess(
                "user-42", "tenant-A", "tenant-A",
                true, false, "device-100", "device-100",
                DeviceManagement.MANAGED,
                DevicePosture.COMPLIANT,
                true, false, NOW,
                ResourceRisk.HIGH);
        assertEquals(DeviceDecision.DENY,
                DeviceTrustPolicy.evaluate(unauthorized, NOW));
    }

    @Test
    void requiresReviewForUnknownCriticalContext() {
        assertEquals(DeviceDecision.REVIEW_REQUIRED,
                DeviceTrustPolicy.evaluate(null, NOW));
        assertEquals(DeviceDecision.REVIEW_REQUIRED,
                DeviceTrustPolicy.evaluate(
                        full(ResourceRisk.HIGH), null));
    }
}
~~~

Các unit tests chỉ chứng minh **logic chính sách giả định**. Chúng không chứng minh MDM/EDR, attestation, IdP hoặc PEP thực sự truyền dữ liệu đúng. Trong hệ thống thật cần integration và end-to-end tests trên các luồng **browser, native app, gateway, API, service mesh, refresh token và direct resource access**.

### 15.3. Dấu hiệu kiểm thử được thiết kế sai

Một test tự tạo một object có deviceId đúng rồi nhận ALLOW chỉ chứng minh điều kiện so sánh. Nó không kiểm tra attacker có thể **giả danh ID đó** hay không.

Một test được phép có kết quả FULL khi attestationVerified=true cũng không chứng minh attestation verifier thực sự xác minh hardware trust chain. Cần test **invalid signatures, wrong issuer/trust anchor, wrong nonce, wrong device key, wrong policy reference, replay và expired appraisal** ở lớp verifier/integration phù hợp.

## 16. Mẫu policy device trust bằng YAML

Mẫu dưới đây thể hiện **nội dung policy cần review**, không phải cấu hình chạy trực tiếp trên một IdP/MDM/vendor cụ thể.

~~~yaml
policy_id: "ZTA-DEVICE-TRUST-006"
policy_version: "2.1"
owner: "<security-access-owner>"
environment: "production"
default_decision: "DENY"
scope:
  applications: ["finance-portal", "finance-api"]
  high_risk_actions:
    - "pii.export"
    - "finance.admin"
    - "billing.approve"
  low_risk_actions:
    - "dashboard.read-limited"
device_evidence:
  accepted_sources:
    - "approved-mdm"
    - "approved-edr"
    - "approved-attestation-verifier"
  require_source_authentication: true
  require_device_session_binding: true
  reject_client_supplied_trust_flag: true
  freshness:
    high_risk_max_age_seconds: 600  # ví dụ nội bộ, không phải chuẩn
    accepted_clock_skew_seconds: 30
  negative_signal_precedence:
    - "REVOKED"
    - "COMPROMISED"
    - "NON_COMPLIANT"
high_risk:
  require:
    - "user_authenticated"
    - "resource_authorized"
    - "tenant_match"
    - "managed_device"
    - "posture_compliant"
    - "fresh_device_evidence"
    - "attestation_verified_when_supported_by_profile"
    - "session_bound_device_identity"
  on_unknown: "DENY"
low_risk:
  require:
    - "user_authenticated"
    - "resource_authorized"
  unverified_device_result: "ALLOW_LIMITED"
  limited_actions: ["dashboard.read-limited"]
  prohibited_while_limited:
    - "data.export"
    - "admin.write"
    - "offline_download"
session:
  reevaluate_on:
    - "new_high_risk_action"
    - "new_or_revoked_device_identity"
    - "critical_edr_or_mdm_signal"
    - "posture_expiration"
  revoke_or_restrict_on_compromise: true
exception:
  approval_required: true
  owner_required: true
  scope_required: true
  expiry_required: true
  audit_required: true
assurance:
  required_evidence:
    - "source_and_appraisal_provenance"
    - "pep_policy_version"
    - "negative_test_results"
    - "device_offboarding_and_revoke_test"
    - "runtime_decision_samples"
~~~

**Đặc biệt:** tên trường attestation_verified_when_supported_by_profile cho thấy chính sách phải phân loại profile. Nếu một loại thiết bị không hỗ trợ attestation đáng tin, không được giả lập PASS; có thể cần chặn HIGH hoặc áp control thay thế đã được phê duyệt. Một trường yêu cầu dưới dạng văn bản không đồng nghĩa engine thực sự enforcement.

## 17. Case study: Zero Trust access cho hệ thống báo cáo tài chính

Giả sử nền tảng báo cáo có các thành phần:

- **Finance portal** sử dụng trình duyệt.
- **Finance API** cung cấp dashboard, báo cáo và export.
- **IdP** xác thực người dùng và session.
- **MDM/UEM** cung cấp status quản lý/patch/encryption.
- **EDR** cung cấp trạng thái agent và cảnh báo.
- **Attestation verifier** áp dụng cho những device profiles có hỗ trợ.
- **ZTNA gateway** làm PEP ở biên.
- **Service policy layer** và **database authorization** bảo vệ tài nguyên.
- **Device registry** quản lý enrollment, certificate, ownership và revoke.

Tài nguyên có ba cấp minh họa: xem dashboard tổng hợp (**LOW**), đọc nội dung báo cáo nội bộ (**MEDIUM**) và xuất bảng chứa PII (**HIGH**).

### 17.1. Ba thiết bị trong cùng một tổ chức

| Thuộc tính | Device A | Device B | Device C |
|---|---|---|---|
| Ownership | Laptop công ty | Laptop công ty | Laptop cá nhân |
| Enrollment | Managed | Managed | Unmanaged |
| MDM posture | Compliant, mới | Compliant nhưng 3 ngày không check-in | Không có nguồn |
| EDR | Healthy, mới | Agent offline | Không biết |
| Device key binding | Được xác minh | Chưa xác minh trên session hiện tại | Không có |
| Attestation | Pass trong phạm vi policy | Chưa có kết quả mới | Không hỗ trợ trong flow |
| User authentication | Đạt | Đạt | Đạt |
| Resource authorization | Đạt cho dashboard/export | Đạt cho dashboard/export | Đạt cho dashboard hạn chế |
| Kết luận device cho HIGH | Có thể đáp ứng khi đủ tất cả các lớp | Không nên ALLOW_FULL từ status cũ | Không đạt profile HIGH |
| Kết luận device cho LOW | Có thể ALLOW_FULL | Có thể LIMITED/STEP_UP theo policy | Có thể LIMITED theo policy |

Device A **không mặc nhiên được export** nếu user không có quyền export hoặc tenant không khớp. Device B không thể lấy MDM compliant cũ làm evidence posture hiện tại. Device C có thể phục vụ đường LOW nếu tổ chức thiết kế limited access, nhưng không nâng quyền HIGH bằng việc tự báo device ID.

### 17.2. Phân tích quyết định trên ba thao tác

**Tình huống 1 — Xem dashboard công việc thông thường**

Người dùng có quyền, dùng BYOD và đã xác thực mạnh nhưng không có MDM. Tổ chức có thể quyết định LIMITED: chỉ hiển thị dữ liệu tổng hợp và không có export. PEP phải kiểm tra đúng operation; không chỉ thay giao diện để ẩn nút download.

**Tình huống 2 — Xuất dữ liệu khách hàng**

Người dùng có role export, nhưng device EDR báo COMPROMISED. Policy cần từ chối hoặc cô lập; việc user có quyền export không ghi đè signal compromised. Đồng thời cần bảo vệ download API, signed URL và storage path để không bỏ qua PEP.

**Tình huống 3 — Truy cập quản trị production**

Thiết bị managed và attested, user có privileged role. Vẫn cần MFA/step-up, approval, JIT/JEA, session monitoring và SoD theo risk. Device trust chỉ là **một điều kiện cần được kiểm chứng**, không thay privileged access governance.

### 17.3. Tính rủi ro khi thiết bị đổi trạng thái giữa phiên

Một user đã có phiên từ Device A. Mười phút sau EDR phát hiện sự kiện nghiêm trọng và đánh dấu compromised. Cần xác định:

- Signal mất bao lâu để tới PIP?
- PDP cache quyết định trước đó bao lâu?
- PEP có biết session/device binding để hạn chế ngay không?
- Refresh token và access token đang phát hành có tiếp tục dùng được không?
- Export request đang chờ có bị dừng không?
- Các đường legacy API có còn chấp nhận token cũ?
- Nhóm SOC/app owner có nhận alert và liên kết được với phiên cụ thể không?

Assurance phải đo thời gian từ sự kiện tới **effective restriction**, không chỉ thời gian MDM cập nhật bảng dashboard.

## 18. Risk → Requirement → Control → Test → Evidence

Một chương trình SECURITY_SECURITY_ASSURANCE cần traceability từ kịch bản rủi ro tới chứng cứ.

| Risk ID | Requirement | Control | Test/assessment | Evidence |
|---|---|---|---|---|
| **RISK-DT-01**: client giả device ID | REQ-DT-01: device identity phải được xác minh, session-bound | CTRL-DT-01: device key/cert proof | Wrong-device binding, forged ID test | Enrollment, binding config, negative results |
| **RISK-DT-02**: posture stale | REQ-DT-02: tín hiệu có freshness phù hợp resource risk | CTRL-DT-02: freshness gate | Stale MDM/EDR heartbeat test | Source timestamps, policy version, PDP decisions |
| **RISK-DT-03**: revoked device vẫn dùng token | REQ-DT-03: access phải hạn chế/revoke sau event phù hợp | CTRL-DT-03: revocation/session controls | Lost-device + replay test | Registry, revocation records, PEP retest |
| **RISK-DT-04**: attacker replay attestation | REQ-DT-04: verifier phải kiểm nonce, signature và binding | CTRL-DT-04: attestation appraisal | Reused nonce, wrong trust anchor/device test | Verifier config, test evidence |
| **RISK-DT-05**: EDR báo compromise nhưng MDM pass | REQ-DT-05: conflict precedence bảo vệ high-risk | CTRL-DT-05: negative signal override | MDM PASS + EDR HIGH test | Policy outcomes, alert correlation |
| **RISK-DT-06**: API bypass gateway | REQ-DT-06: không có đường vào resource không kiểm tra cần thiết | CTRL-DT-06: layered PEP/access path inventory | Direct API/storage/VPN test | Network/API config và negative results |
| **RISK-DT-07**: BYOD bị thu quá nhiều dữ liệu | REQ-DT-07: tối thiểu hóa device telemetry | CTRL-DT-07: privacy-aware collection | Data field review, retention test | PIA, inventory, ingestion schema |
| **RISK-DT-08**: admin đổi compliance policy | REQ-DT-08: policy admin có least privilege và change control | CTRL-DT-08: SoD/PAM/audit | Unauthorized policy edit/rollback test | Approval, audit and config diffs |
| **RISK-DT-09**: không có đường remediation | REQ-DT-09: noncompliance được xử lý có kiểm soát | CTRL-DT-09: quarantine and re-enrollment | Isolation/recovery workflow test | Tickets, state transitions, retest |
| **RISK-DT-10**: thiết bị healthy nhưng user sai quyền | REQ-DT-10: device không cấp business authorization | CTRL-DT-10: resource-level policy | Wrong tenant/action test | Authz logs, integration tests |

Mỗi ID là ví dụ nội bộ của bài. Các điều kiện cụ thể phải được tổ chức định nghĩa theo resource, nghĩa vụ và risk assessment. **Không có một giá trị freshness chung đủ cho tất cả ứng dụng.**

## 19. Ma trận kiểm thử Device trust

Đánh giá thiết kế phải đi cùng thử nghiệm trên những đường có thể xảy ra trong thực tế. Không chạy thử thâm nhập hoặc gây lỗi trên production ngoài phạm vi được ủy quyền.

| Test ID | Tình huống | Kết quả kỳ vọng | Evidence phù hợp |
|---|---|---|---|
| **TEST-DT-01** | Managed, compliant, fresh, bound; user có quyền HIGH | Có thể ALLOW_FULL theo policy | Request, device appraisal, PEP decision |
| **TEST-DT-02** | Thiết bị đáp ứng posture nhưng user không có resource role | DENY | Authz negative test |
| **TEST-DT-03** | User tenant A yêu cầu dữ liệu tenant B | DENY | Cross-tenant E2E |
| **TEST-DT-04** | Client gửi deviceTrusted=true tự khai | Không tin/trong hệ độc lập | API header spoof test |
| **TEST-DT-05** | Device B dùng device ID/certificate giả của A | Không bypass identity/session binding | Wrong key/device test |
| **TEST-DT-06** | Attestation evidence được replay | Reject theo nonce/freshness policy | Verifier test |
| **TEST-DT-07** | Attestation signature không hợp lệ | Reject | Crypto verifier test |
| **TEST-DT-08** | Attestation từ trust anchor khác policy | Reject hoặc REVIEW | Trust-chain negative test |
| **TEST-DT-09** | MDM posture stale cho action HIGH | DENY | Clock/freshness test |
| **TEST-DT-10** | EDR báo COMPROMISED, MDM vẫn COMPLIANT | DENY/quarantine theo precedence | Conflict test |
| **TEST-DT-11** | Device mất management enrollment | Không còn HIGH access | Offboarding/unenrollment |
| **TEST-DT-12** | Device bị đánh dấu LOST/REVOKED | Session/token bị hạn chế theo objective | Revocation E2E |
| **TEST-DT-13** | Token copy từ device A sang B | Không bypass session-bound policy | Token replay/binding test |
| **TEST-DT-14** | Device MDM offline, provider signal UNKNOWN | Không fail-open cho HIGH | Outage/failure injection |
| **TEST-DT-15** | BYOD hợp lệ nhưng thiếu signals cho LOW | LIMITED nếu policy cho phép; không export | Limited-mode E2E |
| **TEST-DT-16** | LIMITED client gọi endpoint export trực tiếp | DENY | PEP + backend authorization |
| **TEST-DT-17** | Quarantine client gọi remediation URL | Chỉ remediation path được phép | Network/app policy test |
| **TEST-DT-18** | Quarantine client dùng VPN/API legacy | Không bypass | Access-path review |
| **TEST-DT-19** | Posture đổi sau user login | Decision được reevaluate trong khoảng đã cam kết | Time-to-restriction measurement |
| **TEST-DT-20** | Có certificate nhưng không có compliant posture | Certificate không tự nâng thành device compliant | Independent signal test |
| **TEST-DT-21** | Admin thay policy từ deny sang permissive | Phê duyệt/alert/change evidence đúng | PAM/SoD test |
| **TEST-DT-22** | Re-enrollment của device khác cùng asset ID | Không kế thừa trust trái phép | Device lifecycle test |
| **TEST-DT-23** | MDM timestamp nằm trong tương lai bất thường | Không coi là fresh mặc định | Clock-skew test |
| **TEST-DT-24** | Browser/native/desktop app có đường truy cập khác nhau | Mọi đường chịu cùng yêu cầu hoặc exception được kiểm soát | Channel coverage |
| **TEST-DT-25** | Device trust signal được ghi vào audit log | Không lộ raw telemetry/PII không cần | Privacy/log inspection |
| **TEST-DT-26** | Chính sách mới tăng yêu cầu HIGH | Runtime và cached decision theo version mới | Rollout/drift test |

### 19.1. Phân biệt positive, negative và failure-path tests

- **Positive:** thiết bị đủ tiêu chí và user đủ quyền được thực hiện công việc hợp lệ.
- **Negative:** fake ID, wrong tenant, stolen token, revoked device, stale posture hoặc missing authorization phải bị từ chối.
- **Failure path:** MDM/EDR/IdP/PIP/PDP lỗi, clock skew, cache stale hoặc audit pipeline gián đoạn phải có hành vi phù hợp policy.
- **Lifecycle:** enroll, patch, re-enroll, ownership transfer, lost, revoke và retire.
- **Operations:** trong một kỳ, các quyết định bất thường, incident, exceptions và remediation có được theo dõi/đóng bằng chứng không?

Một test thành công chỉ chứng minh điều đã thử trong môi trường/version cụ thể. Không được suy ra policy hoạt động trên mọi thiết bị và mọi access path.

### 19.2. Test dữ liệu nhạy cảm an toàn

Cần sử dụng principal, devices và data sets kiểm thử đã được cho phép. Không tự thử đánh cắp token hoặc bypass máy người khác. Với production, ưu tiên có kiểm soát qua canary/synthetic identity hoặc review config và logs; các thử nghiệm phá hoại, revoke hàng loạt, forced quarantine và firmware attestation phải có kế hoạch tránh ảnh hưởng vận hành.

## 20. Evidence cho Device trust: không chỉ là “MDM compliant”

Một evidence set có độ tin cậy cần gắn với **claim, scope, phiên bản, môi trường và thời điểm**.

| Evidence loại | Ví dụ | Câu hỏi chất lượng |
|---|---|---|
| **Inventory** | Device ID, owner, type, status, managed domain | Có đủ thiết bị/phiên thuộc scope? |
| **Enrollment** | Certificate issuance, registration approvals, key attributes | Identity có được tạo/cấp đúng không? |
| **Attestation** | Verifier result, trust anchor, nonce, measurements policy | Bằng chứng này thực sự hỗ trợ thuộc tính nào? |
| **MDM/UEM** | Compliance state, policy version, last check-in | Có đủ mới và được lấy qua API đáng tin? |
| **EDR** | Agent health, incidents, risk signals | Có false negative và xung đột với MDM không? |
| **Session** | User identity, device key binding, token audience/expiry | Session có thể bị replay trên device khác không? |
| **Decision** | PDP decision, resource tier, attributes, policy version | PEP có thực thi đúng decision? |
| **Enforcement** | Gateway/backend config, direct-path probes | Có đường bypass hoặc cached ALLOW không? |
| **Lifecycle** | Lost-device, revoke, re-enroll, decommission | Effective access đã bị thu hồi? |
| **Operations** | Findings, alerts, incident, periodic policy review | Control có hoạt động trong kỳ? |
| **Privacy** | Telemetry field inventory, retention, access audit | Có thu quá mức để chứng minh trust không? |

### 20.1. Chất lượng evidence

**Relevance:** hỗ trợ đúng thuộc tính cần chứng minh.

**Completeness:** bao phủ thiết bị, user sessions, đường access, loại resource và thời kỳ.

**Provenance:** biết nguồn phát tín hiệu, trust anchor, system ID và thời gian.

**Integrity:** tín hiệu/evidence được bảo vệ khỏi chỉnh sửa trái phép; audit logs có quyền và retention phù hợp.

**Freshness:** phù hợp thời điểm quyết định và chính sách nguồn.

**Repeatability:** có test procedure và expected outcomes.

**Limitations:** ghi rõ thiết bị hoặc OS không hỗ trợ attestation, một số provider APIs không cho thấy thông tin chi tiết, hoặc không thể xác minh trạng thái runtime tuyệt đối.

**Privacy:** evidence không đưa raw device fingerprints, geolocation hoặc nhân dạng không cần thiết vào kho audit rộng quyền.

### 20.2. Device evidence có tính thời gian

Một snapshot policy cho thấy MDM đánh dấu COMPLIANT vào 09:00. Nó không chứng minh device đang compliant tại 14:00 nếu chính sách yêu cầu recheck trong thời gian ngắn hơn.

Assurance case cần phân biệt:
- Evidence **về thiết kế** (policy/architecture).
- Evidence **về implementation** (code/config/verifier).
- Evidence **về hoạt động trong kỳ** (actual decisions, signals, sessions).
- Evidence **sau remediation** (new policy/release + retest).

## 21. Claim – Argument – Evidence cho Zero Trust device assurance

Một assurance case mẫu:

| Thành phần | Ví dụ |
|---|---|
| **Risk** | Thiết bị bị chiếm hoặc không quản lý sử dụng credential hợp lệ để export dữ liệu khách hàng |
| **Claim** | Trong scope finance portal/finance API production và kỳ đánh giá, thao tác HIGH chỉ được thực hiện khi user được xác thực/ủy quyền và có device evidence đáp ứng policy hiện hành, fresh và được binding với session |
| **Argument** | Identity/device key được kiểm; posture từ nguồn đáng tin; attestation đánh giá theo profile; PDP xét risk; PEP chặn các đường; revoke/quarantine và monitoring có hiệu lực |
| **Control evidence** | Enrollment, MDM/EDR, verifier policy, device/session binding, authorization configuration |
| **Test evidence** | Stale/forged/revoked/token replay tests, cross-tenant tests và PEP bypass probes |
| **Operating evidence** | Decision samples, policy version logs, lost-device incident, revocation/recheck durations |
| **Assumptions** | Device registry/MDM/EDR/verifier đáng tin trong phạm vi controls, clocks và signal delivery đủ ổn định |
| **Limitations** | Một desktop legacy client không hỗ trợ binding; một BYOD flow chỉ có limited access; một endpoint chưa có runtime test |
| **Residual risk** | Endpoint bị compromise sau attestation, detection delay, client-side malware hoặc session theft trong cùng thiết bị |
| **Conclusion** | PASS/FAIL/INCONCLUSIVE theo scope, không tuyên bố “mọi thiết bị đều an toàn tuyệt đối” |

### 21.1. Claim phải đúng phạm vi

Không viết: “Hệ thống đã dùng Zero Trust nên không có thiết bị nào bị xâm nhập”.

Nên viết có giới hạn: “Đối với các phiên truy cập tài nguyên HIGH thuộc môi trường/version đã đánh giá, PEP yêu cầu identity, authorization, device posture và binding theo baseline; những case đã kiểm thử đáp ứng kỳ vọng, với các ngoại lệ đã ghi.”

Tính năng **không bao giờ có thể chứng minh trực tiếp** chỉ từ MDM dashboard là “thiết bị không có malware”. Tín hiệu EDR/attestation chỉ hỗ trợ một số khẳng định theo khả năng của chúng.

### 21.2. Design, implementation và operating effectiveness

| Mức | Câu hỏi | Evidence |
|---|---|---|
| **Design effectiveness** | Policy có phân tầng resource, xác minh nguồn, freshness/binding, xử lý stale/revoke và fail-safe không? | Architecture, data flow, threat model, baseline |
| **Implementation effectiveness** | Đường IdP/PIP/PDP/PEP, verifier, API và backend thực thi đúng thiết kế? | Code/config, negative tests, version mapping |
| **Operating effectiveness** | Trong kỳ, device enrollment, posture, restricted sessions, exceptions và revocations có hoạt động đúng? | Population, event log, session audit, case samples |
| **Remediation effectiveness** | Sau finding, bypass/freshness bug đã được sửa và kiểm chứng ở production? | Root cause, deployment, regression E2E, runtime evidence |

Không thay **operating evidence** bằng một sơ đồ kiến trúc. Một bài unit test cũng không thể thay cho device attestation verification hoặc resource-level authorization integration.

## 22. YAML: hồ sơ Device trust assurance mẫu

Hồ sơ sau chỉ minh họa cách lưu traceability. Các giá trị PENDING/INCONCLUSIVE là cố ý, không phải kết quả thật.

~~~yaml
device_trust_assurance_id: "DT-ASSURE-006"
module: "SECURITY_SECURITY_ASSURANCE"
assessment:
  chapter: "Zero Trust assurance"
  subject: "Device trust"
  release: "<release-id>"
  period: "<start-end>"
  result: "INCONCLUSIVE"
scope:
  application: "finance-api"
  environment: "production"
  action: "pii.export"
  resource_risk_tier: "HIGH"
  tenant_scope: ["tenant-A"]
  access_paths: ["ztna-gateway", "api-gateway", "backend-api"]
subject:
  identity_ref: "<verified-principal-id>"
  entitlement_ref: "<resource-permission-decision>"
  session_ref: "<minimized-session-id>"
device:
  inventory_ref: "<device-registry-key>"
  owner_ref: "<authorized-owner-reference>"
  enrollment:
    source: "<approved-mdm>"
    status: "MANAGED"
    verified_at: "<ISO-8601>"
    certificate_or_key_ref: "<protected-key-reference>"
  posture:
    source: "<mdm-edr-source-list>"
    policy_id: "<approved-compliance-policy>"
    policy_version: "<version>"
    observed_at: "<ISO-8601>"
    state: "COMPLIANT"
    edr_risk: "NONE_REPORTED"
    evidence_ref: "<posture-appraisal-evidence>"
  attestation:
    profile: "<device-profile>"
    verifier_ref: "<verified-attestation-verifier>"
    reference_policy_ref: "<reference-values-version>"
    session_binding_verified: "PENDING"
    appraisal: "PENDING"
decision:
  pdp_policy_id: "ZTA-DEVICE-TRUST-006"
  pdp_policy_version: "2.1"
  pep_enforcement_ref: "<request-trace>"
  outcome: "PENDING"
  reason_codes:
    - "ASSURANCE_EVIDENCE_PENDING"
  effective_time: "<ISO-8601>"
lifecycle:
  last_successful_check_in: "<ISO-8601>"
  revocation_test_ref: "<negative-test-id>"
  quarantine_test_ref: "<negative-test-id>"
  offline_grace_policy_ref: "<policy-reference>"
controls:
  - control_id: "CTRL-DT-01"
    test_ids: ["TEST-DT-04", "TEST-DT-05"]
    evidence_refs: ["<device-binding-test-report>"]
  - control_id: "CTRL-DT-02"
    test_ids: ["TEST-DT-09", "TEST-DT-23"]
    evidence_refs: ["<freshness-test-report>"]
  - control_id: "CTRL-DT-06"
    test_ids: ["TEST-DT-18", "TEST-DT-24"]
    evidence_refs: ["<access-path-coverage>"]
assurance:
  reviewer: "<independent-assessor>"
  findings: ["<finding-id-or-none>"]
  assumptions:
    - "Approved posture providers are available and verified"
  limitations:
    - "Legacy API access path not yet end-to-end tested"
  residual_risk_owner: "<risk-owner>"
  review_due: "<date>"
reassessment_triggers:
  - "Device profile, MDM or EDR policy/version change"
  - "IdP, binding, token or attestation implementation change"
  - "Lost device, critical incident or bypass finding"
  - "New resource tier or direct access path"
~~~

**Không ghi** raw access tokens, device private keys, firmware secrets hoặc dữ liệu người dùng không cần thiết trong hồ sơ. Nếu cần tham chiếu tới logs chi tiết, dùng evidence IDs có phân quyền và retention thích hợp.

## 23. Finding mẫu: tin compliance cũ khi MDM mất kết nối

Một ứng dụng finance API yêu cầu thiết bị compliant khi export PII. Sau sự cố, auditor thấy gateway dùng giá trị compliance trong cache mà không kiểm tra tuổi tín hiệu; laptop mất liên lạc với MDM trong nhiều ngày vẫn được phép export.

| Trường | Ví dụ |
|---|---|
| **Finding ID** | FND-DT-006 |
| **Criteria** | REQ-DT-02: posture cho action HIGH phải có freshness đã phê duyệt |
| **Condition** | Policy gateway nhận cached COMPLIANT không kèm thời điểm observedAt đủ tin cậy |
| **Evidence** | PIP/PEP config, MDM last check-in, staged stale-signal negative test |
| **Risk** | Thiết bị không còn được giám sát có thể tiếp tục truy cập dữ liệu nhạy cảm |
| **Root cause cần xác minh** | Không có freshness gate; gateway cache được cấu hình theo availability mà thiếu threat review |
| **Immediate action** | Giới hạn HIGH khi signal quá hạn, review affected sessions |
| **Owner** | IAM/Zero Trust platform + endpoint management + finance app owner |
| **Khắc phục** | Gắn source timestamp/policy version, enforce TTL theo risk, xử lý UNKNOWN/DENY và alert feed outage |
| **Verification** | Test đúng tuổi/mốc biên, clock skew, MDM outage, cached decision, production PEP trace và token replay |
| **Residual risk** | Detection gap trong khoảng posture còn hợp lệ; legacy access paths cần xác minh riêng |

Không đóng finding chỉ vì sửa TTL của cache. Cần xem **quyết định ở backend**, các route direct, IdP session/token persistence, app-specific exception và trạng thái triển khai thực tế.

## 24. Audit Device trust: kiểm tra population trước khi lấy mẫu

Một auditor không thể đánh giá chương trình device trust chỉ bằng cách mở dashboard MDM và xem tỷ lệ “compliant”.

### 24.1. Population bao gồm gì?

Trong phạm vi đánh giá, cần đối chiếu:

- Thiết bị được cấp, BYOD đăng ký, contractor và shared/kiosk devices.
- Device certificates/keys và enrollment/retirement records.
- MDM/UEM và EDR sources, policy versions, exceptions.
- Các ứng dụng, APIs, tài nguyên HIGH/MEDIUM/LOW, access paths.
- User/device sessions và những request đã được PEP đánh giá.
- Devices có trạng thái OFFLINE/UNKNOWN/REVOKED/LOST/UNMANAGED.
- Các thiết bị có quyền access nhưng **không nằm trong MDM inventory**.
- Thao tác admin thay đổi compliance và device trust policies.
- Break-glass/exception và temporary access.
- Incident/quarantine/remediation cases và failed evidence collection.

Nếu chỉ lấy mẫu từ danh sách thiết bị **đã managed**, chương trình sẽ bỏ sót chính những thiết bị **unmanaged nhưng vẫn truy cập resource**. Population nên được đối chiếu từ IdP sessions, ZTNA/PEP logs, MDM inventories và application access records.

### 24.2. Ví dụ kiểm toán lấy mẫu

Giả sử có 300 phiên truy cập tài nguyên HIGH trong kỳ. Auditor chọn 30 phiên bằng phương pháp phù hợp và phát hiện 4 phiên không có đủ provenance/freshness evidence. Kết luận chắc chắn từ mẫu là **4/30 phiên đã kiểm tra thiếu evidence**. Không tự suy ra 13,3% toàn bộ population vi phạm nếu mẫu không được thiết kế hỗ trợ thống kê.

Còn cần xem **những request được phép qua access path chưa có log/PEP**. Nếu denominator bỏ sót direct API, tỷ lệ đánh giá từ gateway log sẽ tạo cảm giác an toàn giả.

### 24.3. Evidence cần kiểm tra theo thời gian

- Policy phiên bản nào có hiệu lực vào ngày đó?
- Device được đánh giá lúc nào? Nguồn dữ liệu là gì?
- User identity/authorization có thay đổi sau login?
- Có EDR signal xấu hoặc revocation event trước request không?
- PEP có phản hồi decision và thực sự chặn request?
- Kết quả có đúng với action/resource sensitivity?
- Nếu dùng exception, người phê duyệt, phạm vi, expiry và compensating control là gì?
- Dữ liệu raw nào đã dùng để dựng audit evidence và có được bảo vệ không?

## 25. Metrics và giới hạn diễn giải

| Metric | Ý nghĩa | Không chứng minh |
|---|---|---|
| **Device enrollment coverage** | Tỷ lệ thiết bị trong scope có enrollment theo profile | Enrollment không chứng minh posture hiện tại |
| **Fresh posture coverage** | Device decisions có signal đủ mới / decisions cần signal | Signal mới không chứng minh thiết bị không bị compromise |
| **High-risk enforcement coverage** | HIGH access paths thực sự có PEP/device gate | Policy có hiệu lực nếu paths chưa kiểm thử |
| **Device-session binding coverage** | Phiên có verified binding theo cơ chế phù hợp | Không thể bị lạm dụng trên cùng thiết bị |
| **Unknown/Offline device count** | Thiết bị/tín hiệu chưa xác định trạng thái | Không nên gộp UNKNOWN với COMPLIANT |
| **Critical negative signal response latency** | Thời gian từ signal đến effective restriction | Mọi session đều revoke tức thì |
| **Revoked device access attempts** | Yêu cầu từ identity/device đã bị revoke | Không tự phản ánh số vụ compromise thành công |
| **Quarantine recovery duration** | Thời gian khắc phục tới re-verification | Không được dùng để ép nhân viên bỏ qua bảo mật |
| **Attestation appraisal coverage** | Đường/resource cần attestation có evidence phù hợp | Attestation pass = malware-free |
| **Policy exceptions past expiry** | Các ngoại lệ hết hạn vẫn active | Ít exception không tự chứng minh policy tốt |
| **MDM/EDR feed freshness** | Tuổi của dữ liệu tín hiệu nguồn | Không đảm bảo provider không bị compromise |
| **Direct-path bypass findings** | Các đường không qua PEP phù hợp | Không có finding = không có bypass |
| **Device telemetry minimization** | Tỷ lệ fields có rationale/retention | Không thay PIA và privacy review |

### 25.1. Ví dụ tính toán có scope rõ

Giả định có **200 requests HIGH** từ các paths đã inventory trong một kỳ, 180 request có posture được đánh giá đủ mới theo chính sách, 12 request bị chặn vì stale và 8 request thiếu evidence do lỗi PIP. Có thể báo:

**Fresh-evidence coverage trong population đã quan sát = 180 / 200 = 90%**.

Không được nói “90% thiết bị an toàn” hoặc “90% Zero Trust hiệu quả”. Ngoài ra, nếu chỉ nhìn requests thành công thì 12/8 requests bị chặn/UNKNOWN có thể bị loại khỏi denominator, khiến metric sai lệch. Cần công bố **scope, denominator và định nghĩa trạng thái**.

## 26. Governance và RACI cho Device trust

| Vai trò | Trách nhiệm chính |
|---|---|
| **Security architect / Zero Trust owner** | Xác định trust model, resource tiers, policy decision và evidence criteria |
| **Endpoint management / UEM** | Enrollment, device inventory, posture baseline, lifecycle và remediation |
| **EDR/SOC owner** | Threat signals, incident/quarantine và response |
| **IAM/IdP owner** | User/device identity, session/token binding, conditional access và revoke |
| **Attestation engineer/verifier owner** | Trust anchors, reference values, verifier policy, nonce và appraisal |
| **Application/data owner** | Resource classification, action scope, PEP/backend authorization và business impact |
| **Platform/network owner** | ZTNA gateway, access paths, segmentation, availability và DR |
| **Privacy/Legal** | Xác định scope thiết bị/telemetry, notice, retention và nghĩa vụ |
| **Risk owner/approver** | Quyết định exception/residual risk đúng thẩm quyền |
| **Auditor/independent assessor** | Đánh giá population, validity của evidence, control effectiveness và findings |

### 26.1. Separation of duties cho tín hiệu và policy

Nếu một admin có thể tự thêm device, đổi compliance policy, tạo exception, tắt logging rồi tự phê duyệt quyền truy cập, nhiều lớp bảo vệ trở thành một control point duy nhất. Cần cân nhắc SoD, PAM, MFA, approval và independent review theo mức rủi ro.

### 26.2. Ngoại lệ và break-glass

Một ngoại lệ HIGH cho thiết bị chưa đủ posture phải có:

- Exception ID, mục đích, người dùng và device scope.
- Resource/actions được phép.
- Người phê duyệt có thẩm quyền và risk rationale.
- Phương án thay thế ít rủi ro (VDI, managed loaner, read-only) đã được xem xét.
- Compensating controls, monitoring, restrictions.
- Thời hạn, owner, điều kiện chấm dứt và hậu kiểm.
- Evidence chứng minh không có bypass rộng hơn scope.

**Không được viết exception “bỏ mọi device check cho tài khoản này vô thời hạn”** nếu không có cơ sở/risk decision đặc biệt và kiểm soát tương xứng.

## 27. Continuous device-trust assurance trong SDLC và vận hành

Device trust là một chương trình thay đổi liên tục: OS/firmware update, device enrollment, credential rotation, MDM agent, IdP tokens, security policies và API paths luôn có thể thay đổi.

| Giai đoạn | Hoạt động | Evidence |
|---|---|---|
| **Architecture** | Data flow, trust boundaries, risk tiers, binding và fail-safe modes | ADR, DFD, threat model |
| **Policy design** | Tín hiệu bắt buộc, nguồn, freshness, decision precedence và limited access | Policy version và rationale |
| **Enrollment** | Device ownership, credential/key lifecycle, initial posture | Enrollment/issuance evidence |
| **Development** | Backend authorization, verified signals, PEP enforcement và safe errors | Code review, unit tests |
| **Integration testing** | MDM/EDR/verifier, wrong binding, stale, revocation và failure paths | E2E test reports |
| **Release** | Policy/config version, app routes, direct-path inventory, exception checks | Release gate và deployment snapshot |
| **Production** | Monitor posture freshness, feed outage, denied access, compromise alerts | Runtime signals, PDP/PEP decision logs |
| **Incident** | Quarantine/revoke/session response, containment và impact | Incident timeline, forensic evidence |
| **Device retirement** | Remove enrollment/credential/session, device disposal theo policy | Offboarding records, revocation retest |
| **Review** | Evidence completeness, vendor/OS changes, new access channels | Audit findings, updated assurance case |

### 27.1. Trigger đánh giá lại

- Đổi MDM/EDR vendor, policy hoặc cách tính compliance.
- Thay TPM/secure boot/attestation implementation hoặc reference measurements.
- Đổi IdP, token binding, certificate issuer hoặc session policy.
- Thêm native app/browser/VDI access path.
- Đổi resource sensitivity hoặc thêm action export/admin.
- Thiết bị bị mất, re-enrolled, thay owner hoặc hết hợp đồng.
- MDM/EDR feed outage, signal spoofing, compromise hoặc false-positive incident.
- Cấu hình PEP/PDP thay đổi hoặc phát hiện đường direct API bypass.
- Thay đổi BYOD/employee privacy rules hoặc scope telemetry.
- Thay cloud/network architecture, vendor hoặc device platform support.

### 27.2. Closed-loop assurance

~~~mermaid
flowchart TD
    A["New device / policy / security signal"] --> B["Identify device, resource and trust scope"]
    B --> C["Verify evidence source, binding, freshness"]
    C --> D["PDP evaluates with user authorization"]
    D --> E["PEP enforces full / limited / deny"]
    E --> F["Collect decision and runtime evidence"]
    F --> G{"Still meets risk requirements?"}
    G -- "Yes, within scope" --> H["Continue monitored access"]
    G -- "No / unknown" --> I["Restrict, quarantine, revoke or step-up"]
    I --> J["Incident or remediation + retest"]
    J --> C
    H --> A
~~~

## 28. Các ngộ nhận phổ biến

| Ngộ nhận | Vì sao sai | Cách đánh giá tốt hơn |
|---|---|---|
| “Thiết bị có serial trong inventory là trusted.” | ID có thể bị giả và inventory stale | Verify enrollment, credential và source |
| “Có certificate thiết bị là luôn compliant.” | Certificate xác minh identity/key possession, không tự đo OS posture | Tách authentication và posture |
| “MDM compliant nghĩa không có malware.” | Policy chỉ đo các tín hiệu cụ thể, có blind spots | Kết hợp EDR/attestation và giới hạn claim |
| “EDR không cảnh báo nghĩa thiết bị sạch.” | Detection không hoàn hảo, agent có thể bị bypass | Review coverage, risk signals và detection gap |
| “Attestation pass nghĩa runtime vĩnh viễn an toàn.” | Attestation có scope/thời gian; runtime thay đổi sau đó | Reevaluate và monitoring |
| “Managed device có thể truy cập mọi dữ liệu.” | User/resource authorization vẫn bắt buộc | Least privilege và tenant isolation |
| “User MFA đủ, không cần device trust.” | Credential đúng vẫn có thể dùng trên host rủi ro cao | Risk-based device signal và session binding |
| “Dán deviceTrusted=true trong request đủ.” | Client tự kiểm soát payload | Trusted PIP, server-side validation |
| “Device A attested thì token dùng trên B cũng an toàn.” | Token bearer có thể replay nếu không binding | Sender constraints và session tests |
| “DPoP/mTLS tự chứng minh OS sạch.” | Chứng minh possession of key hoặc kênh, không tự đo posture | Tách binding và device health |
| “BYOD luôn phải bị cấm.” | Có thể có limited access theo risk/privacy | Phân tầng tài nguyên và compensating controls |
| “Tắt device check khi MDM lỗi để duy trì uptime.” | Fail-open cho HIGH | Thiết kế degraded modes theo risk trước |
| “UNKNOWN tương đương NON_COMPLIANT.” | Hai trạng thái có nguyên nhân khác nhau | Ghi rõ status và policy outcome, tránh false assurance |
| “Revoke certificate nghĩa mọi token đã chết.” | Token/session/cache vẫn có thể còn | Effective restriction test |
| “Deny ở gateway đủ cho toàn hệ thống.” | API/DB/storage legacy có thể bypass | Access-path inventory và defense in depth |
| “Thiết bị được remote wipe tức đã xóa dữ liệu.” | Wipe có thể chưa được nhận, device offline | Xác minh delivery/completion và ghi residual risk |
| “Thu mọi telemetry để có device trust mạnh.” | Tăng privacy risk và attack surface | Minimization, purpose và retention |
| “Có một screenshot dashboard MDM là đủ cho audit.” | Thiếu provenance, binding, PEP enforcement và kỳ | Traceability tới request/decision/tests |
| “Device trust là một boolean không đổi.” | State, risk, owner, session và firmware thay đổi | Continuous reevaluation |

## 29. Bài tập tình huống tổng hợp

Một nền tảng doanh nghiệp cho nhân viên và nhà thầu đọc hồ sơ khách hàng. Kiến trúc có IdP, MDM, EDR, một ứng dụng web, native desktop client, gateway và direct API legacy.

Trong quá trình kiểm toán phát hiện:

1. Laptop công ty có certificate còn hiệu lực nhưng **EDR offline**.
2. MDM compliant được lưu cache 48 giờ mà không xét risk tier.
3. Một user bị lấy bearer token từ laptop managed và token được dùng ở máy cá nhân.
4. Attestation verifier chỉ kiểm signature, không kiểm nonce hoặc device/session binding.
5. Một endpoint export legacy không đi qua gateway Zero Trust.
6. Một tài khoản support có quyền đọc dữ liệu tenant khác dù device compliant.
7. Một BYOD device được đánh dấu “trusted” chỉ vì đã từng đăng nhập thành công.
8. Máy đã mất vẫn còn enrollment ID và refresh token hoạt động.
9. MDM admin có thể đổi compliance policy mà không có approval.
10. Nhóm Security thu toàn bộ danh sách ứng dụng cá nhân từ BYOD dù policy chỉ cần kết quả compliant.

**Hãy thực hiện:**

1. Vẽ DFD và trust boundaries từ endpoint, MDM/EDR, attestation, IdP, PDP/PEP tới API, backend và dữ liệu.
2. Xác định ít nhất **tám risk scenarios** và phân biệt rủi ro identity, posture, binding, authorization, privacy, availability.
3. Phân loại mỗi tín hiệu theo **nguồn, điều được chứng minh, freshness và giới hạn**.
4. Thiết kế policy cho **LOW, HIGH và critical admin**, trong đó UNKNOWN và compromised có hành vi riêng.
5. Giải thích tại sao certificate, device ID, MDM compliant và attestation không thể thay thế nhau.
6. Tạo test plan bao gồm replay attestation, stolen token, stale posture, cross-tenant, direct API bypass và MDM outage.
7. Xác định **device offboarding + session revocation** cần chứng cứ gì trước khi đóng.
8. Thiết kế một phương án truy cập ít xâm lấn hơn cho BYOD mà vẫn bảo vệ dữ liệu.
9. Viết **Claim–Argument–Evidence** có giới hạn và nêu các nơi còn thiếu evidence.
10. Đề xuất finding, owner, remediation, retest và metrics cho các gap.

**Gợi ý đối chiếu:** Các trọng điểm cần khắc phục là **binding token với thiết bị/khóa theo cơ chế hỗ trợ**, kiểm nonce và trust anchor của attestation, giới hạn tuổi posture, chặn bypass API, kiểm tra authorization theo tenant, revoke thiết bị bị mất và bảo vệ policy admin. BYOD không phải lý do để thu dữ liệu cá nhân quá mức. Kết luận tốt phải phân biệt **“thiết bị không đủ evidence”** với **“thiết bị đã được phát hiện bị compromise”**, ghi residual risk và giới hạn kiểm thử.

## 30. Checklist đánh giá Device trust trong Zero Trust assurance

- [ ] Xác định **thiết bị/loại thiết bị, user, workload, environment và access path** thuộc scope.
- [ ] Phân biệt **device identification, enrollment, managed, compliant, attestation và authorization**.
- [ ] Asset/device inventory có owner, policy profile, lifecycle state và reconciled population.
- [ ] Enrollment có xác thực quyền, cấp certificate/key đúng scope và xử lý thất bại.
- [ ] Device identity được chứng minh qua cơ chế phù hợp, không tin ID do client tự khai.
- [ ] Tín hiệu MDM/UEM/EDR có **source authenticity, timestamp, policy version và freshness**.
- [ ] Attestation verifier kiểm trust anchor, chữ ký, nonce, scope và binding nếu profile yêu cầu.
- [ ] Không đánh đồng TPM/secure boot/attestation với đảm bảo runtime luôn sạch.
- [ ] Device/session token binding được kiểm tra trên các đường browser, native và backend tương ứng.
- [ ] User authentication và **business authorization/tenant isolation** độc lập với device trust.
- [ ] Resource/action được phân mức risk và áp điều kiện posture tương xứng.
- [ ] Chính sách có **ALLOW_FULL, LIMITED, STEP_UP, QUARANTINE, DENY, REVIEW** với semantics rõ.
- [ ] UNKNOWN, stale, conflict, revoked và compromised không tự chuyển thành permit.
- [ ] Có precedence khi EDR phát signal nguy cơ nhưng MDM vẫn báo compliant.
- [ ] Policy source-of-truth, PIP/PDP/PEP và version có thể audit và không bị bypass.
- [ ] Đường truy cập trực tiếp API, DB, storage, legacy VPN, CI/CD hoặc vendor đã được đánh giá.
- [ ] Policy failure/MDM outage có **fail-safe/degraded mode** theo resource risk.
- [ ] BYOD/contractor/kiosk/IoT có profile, limitations và compensating controls riêng khi cần.
- [ ] Tín hiệu device trust không được dùng thay grant quyền admin, export hoặc cross-tenant.
- [ ] Có continuous reassessment khi posture/session/device ownership/risk đổi.
- [ ] Session/token/cache được giới hạn hoặc revoke trong khoảng thời gian đã được đánh giá.
- [ ] LOST/REVOKED/OFFBOARDED device có quy trình credential revocation và retest effective access.
- [ ] Quarantine chỉ cho phép remediation paths đã được duyệt; không có bypass tới production.
- [ ] Device management/attestation admin có least privilege, SoD, change control và audit.
- [ ] Privacy review định nghĩa telemetry fields, purpose, notice, retention và BYOD boundaries.
- [ ] Negative tests bao gồm fake ID, replay, stale, wrong binding, wrong tenant, direct API và outage.
- [ ] Evidence liên kết **device → source → timestamp → session → policy → resource/action → PEP decision**.
- [ ] Đánh giá phân biệt **design, implementation, operating effectiveness** và khắc phục finding.
- [ ] Metrics có denominator rõ và không suy đồng nghĩa “compliant” với “không có malware”.
- [ ] Mọi exception có owner, approval, scope, expiry, monitoring và review.
- [ ] Claim nêu rõ **điều đã được chứng minh**, giới hạn với thiết bị/platform và residual risk.
- [ ] Thay IdP, MDM, EDR, verifier, policy, client hoặc access path kích hoạt reassessment.

**Ghi nhớ:** **Device trust** là đánh giá **độ tin cậy có điều kiện và có thời hạn** của thiết bị trong một quyết định truy cập Zero Trust. Để thực hiện tốt, phải kết hợp **device identity, trusted posture sources, attestation khi phù hợp, session binding, resource authorization, freshness, fail-safe enforcement, revocation và giám sát liên tục**. Trong SECURITY_SECURITY_ASSURANCE, kết luận phải dựa trên chuỗi **risk → requirement → control → verified device evidence → policy/PEP decision → negative tests/audit → finding/remediation → reassessment**, không dựa vào một nhãn “trusted” hoặc ảnh chụp dashboard đơn lẻ.

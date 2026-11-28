# Service identity – Bảo đảm danh tính của dịch vụ và workload

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **service identity** (danh tính dịch vụ/workload), phân biệt với tài khoản người dùng, tên dịch vụ, credential, service account, quyền truy cập và bằng chứng danh tính.
- Phân tích **chuỗi tin cậy** từ một workload thực đang chạy tới danh tính được cấp, token/chứng chỉ được trình bày, dịch vụ xác minh và quyết định phân quyền.
- So sánh các cơ chế phổ biến: secret/API key tĩnh, mTLS với chứng chỉ ngắn hạn, OAuth 2.0 client credentials, OIDC/workload identity federation, Kubernetes ServiceAccount và danh tính theo SPIFFE/SPIRE.
- Thiết kế vòng đời **cấp phát – ràng buộc – sử dụng – xoay vòng – thu hồi – hủy** danh tính không phải con người, theo nguyên tắc quyền tối thiểu và tách biệt môi trường.
- Nhận diện rủi ro **mạo danh service, đánh cắp token, confused deputy, dùng nhầm audience, quyền IAM quá rộng, trust sai cấu hình** và biện pháp kiểm soát tương ứng.
- Xây dựng **security requirements, kiểm thử âm/dương, evidence register** và lập luận assurance để kiểm chứng danh tính tại môi trường production.
- Đánh giá tình huống thực tế với ứng dụng Java/Spring Boot và worker chạy Kubernetes, gắn nhận diện danh tính với bảo mật giữa các tenant, audit và remediation liên tục.

## 1. Service identity là gì?

**Service identity** là danh tính mà hệ thống gán và dùng để nhận diện **một dịch vụ, tiến trình, workload hoặc tác nhân phần mềm** khi tác nhân đó giao tiếp với tài nguyên khác hoặc thực hiện một hành động có quyền. Trong hệ thống phân tán, người gọi không phải lúc nào cũng là người dùng; có thể là một pod Kubernetes, máy ảo, batch job, worker queue, serverless function, pipeline CI hay hệ thống đối tác.

Ví dụ: `report-api` nhận yêu cầu xuất báo cáo và gửi một job cho `export-worker`. Worker cần đọc đúng dữ liệu của báo cáo, tạo CSV và ghi file vào object storage. Database/storage không nên chấp nhận mọi yêu cầu chỉ vì nó phát ra từ subnet nội bộ. Chúng cần biết **workload nào đang gọi** và **workload đó có quyền gì**.

Trong module **SECURITY_SECURITY_ASSURANCE**, dịch vụ chỉ được xem là đáp ứng mục tiêu bảo mật khi có **bằng chứng có thể kiểm chứng** về danh tính, cơ chế xác thực, quyền hiệu lực và sự vận hành thực tế: từ risk scenario, security requirements, controls, kiểm thử đến audit, finding và khắc phục. “Đã tạo ServiceAccount” không đồng nghĩa “đã chứng minh dịch vụ được xác thực và được giới hạn quyền đúng”.

### Phân biệt năm khái niệm dễ bị gộp làm một

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Service/workload** | Thành phần phần mềm đang thực thi | `export-worker` pod chạy trong namespace `reporting` |
| **Service identity** | Định danh logic có ý nghĩa với hệ thống tin cậy | URI SPIFFE, principal cloud IAM, danh tính workload trong IdP |
| **Credential** | Bằng chứng/khả năng giúp workload chứng minh danh tính | Private key, certificate, bearer token, signed assertion |
| **Authentication** | Quá trình xác minh credential/danh tính theo trust policy | Resource server kiểm tra chữ ký, issuer, audience và hạn của JWT |
| **Authorization** | Quyết định được thực hiện hành động trên tài nguyên nào | Worker được ghi bucket A nhưng không được đọc bucket B |

**Tên DNS, IP, hostname, namespace hoặc label không tự là bằng chứng xác thực danh tính.** Một attacker có thể giả header `X-Service-Name: export-worker`, thay DNS, chạy tiến trình trong một vùng mạng có quyền hoặc chiếm workload. Danh tính phải được **xác minh bằng một cơ chế tin cậy**, và việc ủy quyền phải được kiểm tra riêng.

**Có token hợp lệ cũng không tự đồng nghĩa được cấp quyền.** Một access token có chữ ký đúng nhưng dành cho dịch vụ khác (sai `aud`) không nên được chấp nhận. Một token hợp lệ cho `report-api` nhưng chỉ có quyền đọc chưa đủ để thực hiện hành động export hay đọc tenant khác.

### Service identity khác user identity thế nào?

User identity thường gắn với con người và vòng đời nhân sự, có thể dùng MFA, phê duyệt từ manager và quản lý phiên. Service identity gắn với **workload và mục đích máy-máy**, thường cần cấp credential tự động, sống ngắn, có thể xoay vòng, tránh thao tác tay và được kiểm soát theo môi trường. Không dùng tài khoản nhân viên hay mật khẩu dùng chung để “đại diện cho hệ thống” khi có giải pháp identity chuyên dụng phù hợp.

Trong tình huống **service thay mặt người dùng**, thường tồn tại **hai danh tính** cần phân biệt:

- **Caller workload identity:** dịch vụ nào đang gọi dịch vụ khác.
- **End-user identity/context:** người dùng nào khởi tạo tác vụ, được phép làm gì và trên đối tượng nào.

Service có quyền gọi nội bộ **không được tự động thừa hưởng mọi quyền của người dùng khác**, cũng không nên bỏ qua kiểm tra tenant vì đã xác thực workload.

## 2. Mô hình danh tính và mức độ bảo đảm

Một định danh được gán phải có một **chủ thể xác nhận** và một **nguồn tin cậy**. Có thể mô tả mỗi service identity theo các thuộc tính:

| Thuộc tính | Câu hỏi | Minh họa |
| --- | --- | --- |
| **Principal ID** | Danh tính ổn định, không trùng lặp được hệ thống tin cậy hiểu là gì? | `spiffe://prod.example/reporting/export-worker` |
| **Workload owner** | Nhóm nào chịu trách nhiệm code, runtime và quyền? | Đội reporting |
| **Environment / boundary** | Identity thuộc production, staging, dev hay một bên đối tác? | Cluster production, namespace reporting |
| **Issuer / trust authority** | Ai có quyền cấp credential khẳng định danh tính này? | Workload IdP, cluster issuer, trust domain |
| **Credential type** | Chứng minh bằng cách nào? | X.509 SVID, JWT/OIDC access token |
| **Audience / relying party** | Credential dành để trình bày với hệ thống nào? | `report-job-api` hoặc STS định nghĩa |
| **Validity / renewal** | Credential có hạn, thu hồi và xoay vòng thế nào? | Credential ngắn hạn, gia hạn tự động |
| **Effective permissions** | Cho phép hành động nào, ở resource nào, với điều kiện nào? | `storage:write` vào prefix của một service |
| **Attestation basis** | Bằng chứng gì để tổ chức cấp danh tính cho workload? | Ràng buộc Pod/ServiceAccount/node/metadata theo policy |
| **Evidence / review** | Làm sao chứng minh identity được dùng đúng ở runtime? | Token claims làm sạch, policy snapshot, negative tests |

**Mức độ bảo đảm danh tính (identity assurance)** không đồng nhất với độ dài key hoặc việc có chứng chỉ. Danh tính có thể được ký bằng thuật toán mạnh nhưng lại được cấp cho **bất kỳ pod nào** do policy attestation sai. Khi đó hệ thống xác minh chữ ký rất tốt nhưng **xác minh sai đối tượng được phép nhận danh tính**.

Một lập luận đầy đủ nên trả lời:

1. **Đúng workload được cấp identity?** Bootstrap, attestation, ownership, separation.
2. **Đúng credential từ issuer được tin?** Trust root, signing keys, TLS/JWKS trust, hạn và thuật toán.
3. **Đúng nơi nhận và ngữ cảnh?** Audience, environment, tenant và mục đích token.
4. **Đúng quyền cho hành động cụ thể?** Principal-to-role/resource policy, điều kiện và explicit deny.
5. **Duy trì đúng theo thời gian?** Rotation, revocation, drift, logging, sự cố và thay đổi deployment.

## 3. Bề mặt tấn công của service identity

Rủi ro danh tính workload thường xuất hiện tại nơi phát hành, lưu giữ, trình bày hoặc đánh giá credential.

| Risk scenario | Điều kiện/điểm yếu | Hậu quả | Control cần cân nhắc |
| --- | --- | --- | --- |
| Token tĩnh bị rò từ repository | Secret được commit hoặc ghi vào image | Mạo danh service qua nhiều môi trường | Workload federation, short-lived credentials, secret scanning |
| Service account dùng chung | Nhiều pod/job cùng một identity và policy rộng | Không phân biệt nguồn sử dụng, blast radius lớn | Identity riêng theo workload/môi trường, quyền tối thiểu |
| API tin header client | `X-Service-Name`/`X-Tenant-ID` không được xác thực | Người ngoài giả service hoặc tenant | Xác thực ở trusted boundary, loại bỏ header không tin cậy |
| JWT kiểm tra chữ ký nhưng bỏ `aud` | Token dành cho service A được gửi tới B | Token substitution/confused deputy | Audience validation, authorization theo dịch vụ nhận |
| Tin issuer quá rộng | Chấp nhận token từ tenant/cluster không được phép | Workload khác mạo danh trong hệ thống | Chính sách issuer/trust domain chặt, trust mapping rõ |
| Mất kiểm soát key/cert | Private key bị sao chép hoặc cert dùng quá lâu | Mạo danh trong cửa sổ hiệu lực | Quản lý key, hạn ngắn, rotation, revocation response |
| Quyền cloud IAM wildcard | Worker có quyền đọc cả dữ liệu không cần | Workload compromise → lộ dữ liệu diện rộng | Resource scope, deny test, review IAM |
| Credential/role không thu hồi khi decommission | Service cũ ngừng nhưng principal vẫn dùng được | Đường vào tồn đọng | Lifecycle inventory, remove trust/role/grants, test revoke |
| Identity được cấp theo nhãn thiếu tin cậy | Pod có thể tự thêm label để nhận danh tính mạnh | Leo thang từ workload thấp lên quyền cao | Attestation attributes tin cậy, admission và policy ownership |
| Log pipeline mất nguồn service auth | Thao tác máy-máy không truy vết | Không đủ khả năng điều tra, false assurance | Audit events, end-to-end ingestion/alert test |

**Không tự suy từ “chạy trong cluster riêng” rằng service an toàn.** Kẻ tấn công có thể đã chiếm pod, credential của developer, pipeline CI hoặc một service ít quyền; phải xem các đường nội bộ và trust boundary như bề mặt tấn công thực.

## 4. Data flow và trust boundary trong một hệ thống Java

Xét luồng xuất báo cáo đa tenant:

~~~mermaid
flowchart TD
    U["User tenant A/B"] --> GW["API Gateway"]
    GW --> API["Spring Boot report-api"]
    IDP["User IdP / OAuth authorization"] --> API
    API --> Q["Export Job Queue"]
    Q --> WORKER["export-worker trong Kubernetes"]
    K8S["ServiceAccount + projected token"] --> WORKER
    WORKER --> STS["Workload federation / STS"]
    STS --> IAM["Cloud workload principal + scoped role"]
    IAM --> DB[("Report database")]
    IAM --> STORE[("Object Storage")]
    WORKER --> INTERNAL["report-job-api / internal service"]
    CA["Service issuer / trust roots"] --> INTERNAL
    WORKER --> LOG["Audit and security telemetry"]
    INTERNAL --> LOG
~~~

Một mô hình thực tế có thể không có đủ mọi thành phần ở trên; sơ đồ chỉ **minh họa các điểm xác thực và ủy quyền khác nhau**.

### Các ranh giới cần bảo vệ

| Trust boundary | Điều thay đổi khi đi qua | Câu hỏi assurance |
| --- | --- | --- |
| Client → API gateway | Request đến từ user/client bên ngoài vùng tin cậy | Ai xác thực user, kiểm tra quyền ở đâu, có tin header không? |
| API → queue | User-initiated action thành job bất đồng bộ | Ai được publish; job chứa tenant/owner đáng tin chưa? |
| Queue → worker | Message trở thành hành động của workload có đặc quyền | Worker xác minh input/owner, có giới hạn theo job không? |
| Worker → issuer/STS | Workload yêu cầu credential hoặc token trao đổi | Issuer dựa vào attestation nào; audience và TTL ra sao? |
| Worker → database/storage | Danh tính máy được dùng để truy cập dữ liệu | IAM có hiệu lực theo action/resource/tenant không? |
| Worker → internal API | Dịch vụ nhận quyết định tin caller | JWT/mTLS được xác thực, bind đúng workload, authZ đúng không? |
| CI/CD → Kubernetes/deployment | Code, image và config đi vào runtime | Ai có thể thay image, ServiceAccount, policy hoặc mount token? |
| Runtime → logging | Sự kiện security được lưu làm bằng chứng | Có nguồn log đầy đủ, không lộ token, đủ khả năng audit? |

### Không truyền nhầm danh tính người dùng thành quyền của worker

`report-api` có thể xác nhận user A được xuất báo cáo R của tenant A và tạo job chứa **ID kết quả đã được ủy quyền**. Worker cần xác minh nguồn job, scope và ràng buộc tenant/job ownership theo thiết kế; không được tin một trường `tenantId` hoặc `reportId` tùy ý từ message mà bỏ qua authorization.

Service identity xác minh **ai là worker**; authorization nghiệp vụ xác minh **worker này có được thực hiện hành động cụ thể thay cho người dùng này không**. Đây là hai kiểm soát độc lập và bổ sung nhau.

## 5. Mô hình xác thực và cơ chế cấp credential

Không có một cơ chế bắt buộc duy nhất cho mọi hệ thống. Cần lựa chọn theo môi trường, ranh giới tin cậy, khả năng của nền tảng, loại dữ liệu, mức rủi ro và yêu cầu vận hành.

| Phương pháp | Cách nhận diện | Ưu điểm | Giới hạn/rủi ro |
| --- | --- | --- | --- |
| **API key/secret tĩnh** | Chứng minh sở hữu giá trị bí mật | Dễ tích hợp với hệ thống cũ | Dễ sao chép/rò; khó truy vết khi dùng chung, rotation phức tạp |
| **Mutual TLS (mTLS)** | Hai đầu xác thực cert và private key trong TLS handshake | Xác thực peer và bảo vệ kênh, thích hợp máy-máy | Cần PKI/rotation; cert hợp lệ chưa tự biểu thị quyền resource |
| **OAuth 2.0 client credentials** | Client được cấp access token từ authorization server | Token giới hạn scope/audience và thời hạn theo thiết kế | Cách client chứng thực với server vẫn phải an toàn; không tự xác minh workload nếu dùng shared secret |
| **Workload identity federation** | Token/assertion của issuer nguồn được bên nhận tin và trao đổi lấy credential giới hạn | Giảm nhu cầu phân phối long-lived cloud keys | Cấu hình issuer/audience/subject trust sai có thể mở quyền rộng |
| **Kubernetes ServiceAccount token** | Token ký cho danh tính ServiceAccount trong cluster | Có thể dùng projected short-lived token và chỉ định audience | Không tự là cloud access token, và cùng ServiceAccount có thể được nhiều pod dùng |
| **SPIFFE/SPIRE** | Xác lập workload identity và phát hành X.509/JWT SVID theo trust domain và attestation | Có định danh workload nhất quán, hỗ trợ mTLS/JWT ở hệ thống phân tán | Cần thiết lập trust, attestation, chính sách cấp và vận hành issuer đúng |
| **Managed workload identity** | Nền tảng cấp identity cho workload/compute resource | Có thể tránh key tĩnh và tích hợp IAM | Cần hiểu mapping từ resource đến principal, quyền và boundaries thực tế |

**Tăng số lớp xác thực không tự bảo đảm quyền tối thiểu.** Một worker có mTLS và token hợp lệ vẫn có thể là nguồn lộ dữ liệu nếu IAM của worker cho phép `storage:*` trên mọi bucket.

### 5.1. Mức tin cậy của API key

API key thường chỉ là **bearer secret**: ai biết giá trị hợp lệ thì có thể sử dụng trong phạm vi cho phép. Nếu phải dùng vì tương thích, nên có:
- Key riêng cho mỗi hệ thống tích hợp/đối tác và environment.
- Phạm vi hành động/resource tối thiểu, hạn và rotation/revocation.
- Lưu trong secret manager phù hợp, không trong repository, log, URL hay image.
- Quản lý người/nhóm sở hữu, phân biệt test với production.
- Giám sát sử dụng bất thường và test việc vô hiệu hóa key cũ.

Không dùng một khóa chung cho tất cả workers rồi coi audit event là bằng chứng có thể phân biệt từng workload.

### 5.2. mTLS và giới hạn của danh tính trong chứng chỉ

Trong mTLS, dịch vụ nhận xác minh chuỗi chứng chỉ theo trust roots thích hợp và chứng chỉ peer; **authorization** sau đó phải map một thuộc tính đã kiểm chứng (SAN, SPIFFE ID hoặc identity được quy định) tới policy cho action/resource.

Cần kiểm tra: issuer/trust domain nào được tin; định danh workload trong cert; thời hạn, EKU/thuộc tính phù hợp; mapping vào quyền; cấp lại key/cert; đường nào có thể gọi không qua mTLS; fallback hoặc proxy termination có làm mất peer identity không.

Nếu TLS bị terminate ở proxy, ứng dụng ở phía sau **không nên tin header mô tả peer identity do client tự đưa**. Phải thiết kế trust giữa proxy và backend, cách chuyển danh tính có bảo vệ và kiểm chứng được; proxy mTLS đạt không mặc định làm mọi API downstream đạt.

### 5.3. OAuth2/OIDC và token cho service

Khi một service cần access token, nó có thể dùng flow/client authentication do tổ chức phê duyệt, hoặc dùng **workload federation** thay secret tĩnh. OAuth2 client credentials phù hợp với một số luồng máy-máy; nhưng **OIDC ID token** và **OAuth2 access token** phục vụ mục đích khác nhau, không được tùy tiện hoán đổi.

- **ID token:** khẳng định một sự kiện xác thực tới **relying party** phù hợp trong OIDC; không mặc định là credential để gọi mọi API.
- **Access token:** dùng để yêu cầu truy cập resource server trong phạm vi, audience/scope, thời hạn và các ràng buộc được xác định.
- **Federation assertion:** token do nguồn identity đáng tin cấp, có thể được một STS hoặc hệ thống tin cậy trao đổi thành credential cho resource đích; không được mặc định coi là cloud key nếu chưa qua bước trao đổi/ủy quyền tương ứng.

Cách xây dựng trust phải dựa trên **issuer và token type cụ thể**, không chỉ “đã có JWT” vì JWT là định dạng, không tự quy định policy.

## 6. Chuỗi bootstrap và workload attestation

Một vấn đề nền tảng là: **làm sao issuer biết ai xứng đáng nhận service identity trước khi workload có credential?**

Thường cần một cơ chế **bootstrap trust** dựa trên thuộc tính runtime/nền tảng và quy trình triển khai:

1. Hệ thống tạo workload theo deployment được phê duyệt: image, namespace, ServiceAccount hoặc instance identity.
2. Runtime/nền tảng cung cấp một số **chứng cứ về ngữ cảnh**: node, Pod, account, service identity hoặc assertion ngắn hạn.
3. Issuer/STS/agent kiểm tra chứng cứ với **trust configuration** và policy cấp danh tính.
4. Nếu phù hợp, cấp credential có giới hạn audience, validity và identity claims.
5. Relying party kiểm tra credential rồi **tự đưa ra authorization decision**.

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant P as Platform identity source
    participant S as Issuer / STS
    participant R as Resource service
    W->>P: Yêu cầu assertion theo workload context
    P-->>W: Short-lived assertion có chữ ký và audience
    W->>S: Trình assertion để trao đổi / xin credential
    S->>S: Xác minh issuer, subject, trust mapping, policy
    S-->>W: Credential/Access token giới hạn
    W->>R: Gọi API với credential
    R->>R: Verify chữ ký, issuer, audience, lifetime
    R->>R: Authorization theo principal/action/resource
    R-->>W: Cho phép hoặc từ chối
~~~

Sơ đồ mô tả một **kiểu triển khai federation**; các hệ thống sử dụng mTLS/SPIFFE hoặc managed identity có trình tự chi tiết khác.

### Tránh “identity theo label có thể tự khai”

Nếu một pod tùy ý có thể thêm label `app=payment` rồi nhận principal `payment-prod`, label đó **không đủ sức làm chứng cứ đáng tin**. Cần xác định ai được quyền tạo/sửa workload, namespace, ServiceAccount, policy attestation, token projected và issuer configuration.

**Attestation không tự chứng minh image/code không độc hại.** Nếu CI/CD đã bị chiếm và deploy mã sai vào đúng ServiceAccount được tin, workload vẫn có thể nhận identity hợp lệ. Identity assurance phải phối hợp **software supply-chain controls, artifact provenance, admission policy, RBAC và bảo vệ CI/CD**, tùy mô hình rủi ro.

### Đánh giá common-cause failures

Một issuer, cluster CA hoặc token-signing key bị lộ có thể ảnh hưởng **nhiều service cùng lúc**. Cần xem trust domain rộng đến đâu, khả năng revoke/rotate, phát hiện bất thường, cô lập môi trường và kế hoạch khi issuer lỗi. Một dashboard chứng minh 50 services có token hợp lệ không chứng minh các services độc lập trước **cùng một compromise**.

## 7. JWT service token: các kiểm tra không thể bỏ qua

Khi sử dụng JWT bearer token cho máy-máy, resource server phải kiểm tra token theo **loại token và hợp đồng tin cậy được phê duyệt**, không chỉ đọc claims sau khi decode Base64.

| Nhóm kiểm tra | Mục tiêu | Nếu bỏ qua |
| --- | --- | --- |
| **Chữ ký và khóa tin cậy** | Token do issuer đáng tin cấp, thuật toán phù hợp | Attacker tự ký token hoặc dùng key ngoài trust |
| **Issuer (`iss`)** | Token phát hành bởi đúng bên được phép | Chấp nhận token từ cluster/tenant/IdP khác |
| **Audience (`aud`)** | Token dành cho resource server đang nhận | Token substitution: token A được dùng ở B |
| **Expiration (`exp`), thời điểm hiệu lực (`nbf`)** | Token nằm trong cửa sổ hợp lệ với chính sách clock skew | Credential hết hạn hoặc chưa hợp lệ được dùng |
| **Subject / principal mapping (`sub` và claim riêng)** | Định danh caller phù hợp với quy ước issuer | Lẫn workload, user, môi trường hoặc dịch vụ |
| **Scope/permission** | Actor có quyền với hành động đang yêu cầu | Token đọc được dùng để thực hiện thao tác ghi |
| **Token type / usage** | Không nhầm ID token, service assertion và access token | Nhận sai loại credential cho API |
| **Trust context / binding** | Policy có cần mTLS/PoP hoặc ràng buộc tenant/resource không | Bearer token bị sao chép có thể được phát lại |
| **Revocation/change handling** | Hệ thống xử lý quyền bị thu hồi và token còn hiệu lực ra sao | Revoke IAM nhưng access token cũ vẫn cho quyền |

**Không lấy các trường được gửi bên ngoài token làm sự thật tin cậy.** Ví dụ `X-Tenant-Id` từ client, `X-Role` hay một claim tùy ý không được issuer tin cậy bảo đảm có thể bị giả mạo. Nếu dùng header từ gateway, phải khóa đường trực tiếp, ngăn client tự set/override và chứng minh quan hệ tin cậy backend.

### Audience, issuer và subject trả lời ba câu hỏi khác nhau

- `iss`: **Ai phát hành?**
- `sub` hoặc claim identity được định nghĩa: **Token nói về chủ thể nào?** Ý nghĩa phải theo hợp đồng issuer.
- `aud`: **Token này dành cho ai nhận?**

Ngay cả khi cả ba hợp lệ, API vẫn phải quyết định **“principal này có được thực hiện action này trên object này không?”**. Đừng chỉ kiểm tra tên service bằng cách so sánh một chuỗi trong request body.

### Bearer-token replay và cách giảm thiểu

JWT có thể có chữ ký đúng, audience phù hợp và còn hạn nhưng **đã bị sao chép từ một workload bị xâm nhập**. Relying party khó phân biệt original với bản sao nếu token thuần bearer.

Các lựa chọn tùy rủi ro gồm: lifetime ngắn và rotation; bảo vệ token ở runtime; hạn chế egress; scope nhỏ; sender-constrained token hoặc mTLS/proof-of-possession khi hạ tầng hỗ trợ; phát hiện sử dụng bất thường; quy trình revoke credential và thay trust. **Audience validation không tự ngăn replay tại chính audience hợp lệ.**

## 8. Kubernetes ServiceAccount và workload federation

Kubernetes `ServiceAccount` cung cấp một danh tính gắn với account trong namespace. Một Pod có thể được cấu hình sử dụng ServiceAccount; token được cấp theo cơ chế nền tảng, và có thể được **projected** dưới dạng token có audience/expiry được xác định.

### Quy tắc thiết kế

- Cấp **ServiceAccount riêng cho workload/nhóm tác vụ** khi cần ranh giới quyền khác nhau; không mặc định dùng `default`.
- Khóa quyền tạo/sửa Pod và khả năng **gán ServiceAccount**; nếu bất cứ ai có quyền chạy Pod dưới ServiceAccount đặc quyền, họ có thể lợi dụng danh tính đó.
- Hạn chế Kubernetes RBAC dành cho ServiceAccount; không cấp `cluster-admin` cho worker bình thường.
- Chỉ mount token đến tiến trình thật sự cần và dùng **audience dành cho bên nhận**. Vô hiệu hóa mount tự động nếu ứng dụng không cần Kubernetes API token.
- Nếu token dùng để federation với cloud, thiết lập **trust mapping (issuer, audience, subject và điều kiện namespace/ServiceAccount)** tại bên nhận; token Kubernetes không tự trở thành cloud credential.
- Thiết kế rotation/renewal: ứng dụng phải đọc credential cập nhật, không giả định file token sẽ không đổi.
- Tách production và non-production identities/trust, hạn chế quyền gọi chéo môi trường.

### YAML minh họa token projected theo audience

Ví dụ chỉ thể hiện cách tạo một Pod dùng ServiceAccount và projected token **cho workload cần trao đổi credential**. Không phải cấu hình vendor STS hoặc policy production hoàn chỉnh:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: export-worker
  namespace: reporting
---
apiVersion: v1
kind: Pod
metadata:
  name: export-worker-example
  namespace: reporting
spec:
  serviceAccountName: export-worker
  automountServiceAccountToken: false
  volumes:
    - name: workload-identity
      projected:
        sources:
          - serviceAccountToken:
              path: token
              audience: "workload-sts.example.internal"
              expirationSeconds: 3600
  containers:
    - name: worker
      image: "registry.example.invalid/report/export-worker:example"
      volumeMounts:
        - name: workload-identity
          mountPath: /var/run/workload-identity
          readOnly: true
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
~~~

**Diễn giải giới hạn của ví dụ:**

1. Audience phải tương ứng với **bên thực sự xác minh token** và chính sách federation, không dùng giá trị giả định ở production.
2. Projected ServiceAccount token có expiry và được Kubernetes hỗ trợ làm mới theo cơ chế projection; ứng dụng phải tương thích với việc thay đổi token. `3600` giây chỉ là giá trị minh họa.
3. `automountServiceAccountToken: false` ngăn mount mặc định, nhưng Pod vẫn có volume projected token **được khai báo rõ** như ví dụ.
4. Image tag `:example` và ServiceAccount name chưa chứng minh image đủ tin hoặc workload đủ quyền; quy trình thật cần xác nhận provenance/deployment, IAM, issuer config, admission và policy cụ thể.
5. File token phải được bảo vệ, không log ra ngoài hoặc gửi tới audience không được phê duyệt.
6. Với một số mô hình cloud, việc exchange token, binding ServiceAccount với cloud IAM role hoặc webhook injection có cấu hình riêng; **không suy ra quyền cloud từ YAML này**.

### Khi nào nên dùng federation?

Federation có giá trị khi workload cần truy cập tài nguyên khác mà không muốn phát tán **long-lived credentials** vào Pod, secret store hoặc CI. Nhưng cần kiểm tra cơ chế **trust giữa cluster issuer và hệ thống nhận**, IAM role mapping, quyền kết nối, lifetimes, failure handling và giới hạn theo môi trường.

Nếu mapping tin **mọi ServiceAccount trong mọi namespace** mà cấp role đọc production data, federation làm giảm rủi ro lưu key tĩnh nhưng lại tạo **rủi ro ủy quyền quá rộng**. Nhận diện danh tính mạnh không sửa được IAM policy quá rộng.

## 9. SPIFFE/SPIRE, mTLS và định danh xuyên nền tảng

SPIFFE mô tả định dạng và mô hình nhận diện workload, thường có **SPIFFE ID** dạng URI:

~~~text
spiffe://example.org/reporting/export-worker
~~~

**SVID** (*SPIFFE Verifiable Identity Document*) là chứng cứ có thể xác minh cho workload identity; có các dạng thông dụng như **X.509-SVID** dùng cho mTLS và **JWT-SVID** dành cho các trường hợp phù hợp. SPIRE là một triển khai hỗ trợ chứng thực và cấp phát SVID dựa trên cấu hình attestation.

### Những điều phải hiểu khi dùng SPIFFE

- **Trust domain:** những authority và trust roots nào được hệ thống chấp nhận?
- **Registration/attestation:** điều kiện nào làm workload được nhận SPIFFE ID?
- **Identity mapping:** service nào được phép có ID nào, trong environment/namespace nào?
- **Credential lifecycle:** khóa/chứng chỉ/token được cấp lại và thay đổi thế nào?
- **Authorization:** bên nhận chấp nhận ID nào cho action/resource nào, không chỉ “cùng trust domain”.
- **Federation:** nếu có nhiều trust domain, ai được phép tin domain nào, theo policy nào?

Ví dụ, hai workload có chứng chỉ hợp lệ trong cùng trust domain **không mặc nhiên có quyền gọi mọi API của nhau**. mTLS giúp xác thực peer và bảo mật kênh; service vẫn cần authorization theo principal và hành động.

**Cẩn trọng với kết luận assurance:** Attestation theo Pod/node selectors, labels hoặc metadata chỉ mạnh đến mức độ tin cậy và quyền sửa những thuộc tính đó. Không phải cứ dùng SPIFFE/SPIRE là tự động chống được workload compromise, CI compromise hoặc insider có quyền cao.

## 10. Ủy quyền theo service identity: tách principal và business context

Ngay sau khi xác thực service, API cần đưa ra quyết định ủy quyền. Một thiết kế hữu ích là mô hình:

\[
\text{Allow} =
\text{AuthenticatedCaller}
\land \text{PermittedAction}
\land \text{PermittedResource}
\land \text{ContextConditions}
\]

Đây là **diễn giải logic**, không phải công thức có thể thay thế policy engine. Điều kiện cụ thể gồm environment, tenant, request origin, time, risk signals, delegated permissions và resource owner.

### Đặt tên service không phải authorization policy

Ví dụ `export-worker` có token `scope=reports.write` nhưng phải thao tác trên `tenant-A` được job đã phê duyệt. API cần kiểm tra:

- Caller identity nào, token có đúng `aud=report-job-api` không?
- Scope có quyền thực hiện action tương ứng không?
- Resource/job có nằm trong phạm vi workload được cấp, và **tenant của người dùng gốc** có phù hợp không?
- Dữ liệu đầu vào có thể bị chỉnh sửa từ queue hoặc client không?
- Có cần ràng buộc job owner, expiry, idempotency và kiểm tra chống phát lại không?
- IAM/storage role của worker có giới hạn đến đúng tài nguyên phải đọc/ghi không?

**Confused deputy** xảy ra khi một dịch vụ có đặc quyền thực hiện hành động ngoài mục đích cho tác nhân ít quyền vì nó tin request hoặc context không đủ. Cần kiểm tra **cả identity của caller lẫn quyền của actor/ngữ cảnh được đại diện**, ở đúng nơi vượt trust boundary.

### Policy dễ bỏ sót trong hệ thống nhiều lớp

| Lớp | Có thể kiểm tra | Không thay thế |
| --- | --- | --- |
| Network/mTLS | Peer, kết nối được phép, service identity của kênh | Quyền cấp đối tượng và tenant |
| Gateway | Token, route, rate limit, một số scopes | Authorization bên trong job/worker khi có đường gọi khác |
| Application | Action, role, object owner, tenant/context | IAM permission cho storage/database trực tiếp |
| Cloud IAM/resource policy | Workload principal, resource/action, conditions | Quyền nghiệp vụ của end-user khởi tạo job |
| Queue/consumer | Producer identity, message integrity, job authorization | Kiểm tra quyền tại API đối với user ngoài hệ thống |
| Monitoring | Hành động, lạm dụng và thay đổi policy | Cơ chế preventive nếu hậu quả xảy ra trước alert |

Việc “đã có gateway validate JWT” không cho phép worker tin mọi message nội bộ, và không đủ để cấp `storage:*` cho mọi service.

## 11. Java/Spring Boot: xác minh JWT inbound đúng nguồn và audience

Một Spring Boot 3 / Spring Security 6 resource server có thể xác minh JWT bearer token dành cho **internal API**. Ví dụ sau minh họa **chữ ký RS256 từ JWKS được tin, issuer, audience, hạn token và scope**; URL và audience là dữ liệu giả định để học.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WorkloadApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.POST, "/internal/report-jobs/**")
                    .hasAuthority("SCOPE_reports.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        // Hai địa chỉ dưới đây chỉ minh họa: phải lấy từ
        // trust configuration/JWKS metadata được phê duyệt.
        String issuer = "https://identity.example.invalid/workloads";
        String jwkSetUri = "https://identity.example.invalid/keys";
        String expectedAudience = "report-job-api";

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(expectedAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Invalid audience", null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        return decoder;
    }
}
~~~

### Chính xác ví dụ này chứng minh điều gì?

- Chỉ chấp nhận JWT được xác minh bằng khóa từ **JWKS cấu hình tin cậy** và thuật toán được chọn trong ví dụ, đồng thời kiểm tra issuer, audience và timestamp theo validator.
- Đường `POST /internal/report-jobs/**` yêu cầu authority `SCOPE_reports.write` theo quy tắc mapping mặc định cho claim scope phù hợp.
- Những đường khác bị từ chối theo `anyRequest().denyAll()`, ngoại trừ health endpoint minh họa.

**Chưa đủ để coi là ứng dụng production hoàn chỉnh:**

1. URL issuer/JWKS, thuật toán được chấp nhận, key rotation, network egress và trust store phải được cấu hình đúng theo issuer của hệ thống thực.
2. Phải xác minh **đúng loại access token** và danh tính workload qua claims đã được issuer định nghĩa. Scope một mình chưa cho biết chỉ `export-worker` được phép gọi.
3. Spring Security yêu cầu dependency resource server và các cấu hình ứng dụng phù hợp; đoạn code giả định dependency đã được cài.
4. `permitAll()` cho health là lựa chọn minh họa; môi trường thực cần xem ingress/network và nội dung response.
5. Cần quyết định CSRF/session policy theo mô hình ứng dụng; ví dụ không tự tắt mọi cơ chế bảo vệ khi chưa biết client.
6. Nếu resource server đứng sau proxy, không tin danh tính từ header không xác thực.
7. Phải kiểm tra quyền **đối tượng, tenant, job** ở tầng nghiệp vụ. `SCOPE_reports.write` không chứng minh worker được phép tạo job cho tenant khác.
8. Không đọc token bằng cách decode Base64 rồi tin claim; việc xác minh cần qua resource server hoặc cơ chế đáng tin tương đương.
9. Token bearer có thể bị dùng lại trước expiry nếu bị đánh cắp; xem xét scope hẹp, lifetime ngắn, network restriction, sender constraints hoặc mTLS theo threat model.

### Service identity phải được gắn với policy rõ

Giả sử chỉ một nhóm workload đã đăng ký có quyền tạo job. Sau khi xác thực JWT, tầng ủy quyền có thể kiểm tra **principal/claim được issuer bảo đảm**, scope, service registry và quyền trên tenant/resource; không dựa chỉ vào `scope` hoặc một chuỗi tự khai từ request body.

Ví dụ một policy checker (dữ liệu `callerPrincipal` phải lấy từ **trusted authenticated context**, không lấy từ header phía client):

~~~java
import java.util.Set;

public final class ServiceJobPolicy {
    private static final Set<String> APPROVED_CALLERS =
        Set.of("reporting/export-worker", "reporting/scheduled-export");

    public boolean maySubmitJob(
            String callerPrincipal,
            Set<String> validatedScopes,
            String requestedTenant,
            Set<String> permittedTenants) {

        return APPROVED_CALLERS.contains(callerPrincipal)
            && validatedScopes.contains("reports.write")
            && requestedTenant != null
            && permittedTenants.contains(requestedTenant);
    }
}
~~~

Đây là **logic minh họa**, không phải công cụ xác minh JWT. `permittedTenants` cũng phải do chính sách và dữ liệu đáng tin cung cấp; không được lấy từ một danh sách tenant do caller tùy ý gửi. Trong dự án thật, danh tính/claims được chuẩn hóa theo issuer và policy đã version, không hardcode allowlist rồi bỏ qua quy trình thay đổi.

## 12. Ví dụ kiểm thử service policy và verification outcomes

Các unit tests sau chỉ xác nhận logic quyết định sau khi một hệ thống khác đã **xác minh** danh tính và scopes:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;
import org.junit.jupiter.api.Test;

class ServiceJobPolicyTest {
    private final ServiceJobPolicy policy = new ServiceJobPolicy();

    @Test
    void approvedWorkerMaySubmitInPermittedTenant() {
        assertTrue(policy.maySubmitJob(
            "reporting/export-worker",
            Set.of("reports.write"),
            "tenant-A",
            Set.of("tenant-A")));
    }

    @Test
    void unknownServiceCannotReuseScope() {
        assertFalse(policy.maySubmitJob(
            "unknown/service",
            Set.of("reports.write"),
            "tenant-A",
            Set.of("tenant-A")));
    }

    @Test
    void validServiceCannotCrossTenantBoundary() {
        assertFalse(policy.maySubmitJob(
            "reporting/export-worker",
            Set.of("reports.write"),
            "tenant-B",
            Set.of("tenant-A")));
    }

    @Test
    void readOnlyScopeCannotSubmitJob() {
        assertFalse(policy.maySubmitJob(
            "reporting/export-worker",
            Set.of("reports.read"),
            "tenant-A",
            Set.of("tenant-A")));
    }
}
~~~

**Unit tests trên không kiểm chứng JWT issuer/audience, Kubernetes/STS trust hoặc cloud IAM.** Chúng chỉ thuộc lớp application policy. Muốn kết luận service identity an toàn, cần kiểm thử integration và runtime với token đã ký từ issuer thử nghiệm phù hợp, resource server, network policy và effective permissions.

### Test plan theo security requirements

| Test ID | Trường hợp | Expected result |
| --- | --- | --- |
| **SID-T01** | Workload hợp lệ dùng access token đúng issuer, audience, scope | Được phép gọi đúng API/action theo policy |
| **SID-T02** | Không gửi token hoặc gửi token sai chữ ký | Bị từ chối trước khi xử lý nghiệp vụ |
| **SID-T03** | Gửi token đúng chữ ký nhưng sai `aud` | Bị từ chối bởi resource server |
| **SID-T04** | Token từ issuer/cluster không được tin | Bị từ chối, không được map sang principal đặc quyền |
| **SID-T05** | Token hết hạn hoặc chưa tới thời điểm hiệu lực | Bị từ chối theo chính sách thời gian |
| **SID-T06** | Caller hợp lệ nhưng thiếu scope/hành động | Bị từ chối tại authorization |
| **SID-T07** | Worker tenant A yêu cầu job tenant B | Không thực hiện trái quyền; không tạo dữ liệu cross-tenant |
| **SID-T08** | Mạo header tên service, role hoặc tenant | Không thay đổi authenticated identity/permission |
| **SID-T09** | Đi vòng ingress/gateway qua cổng nội bộ | Truy cập bị chặn hoặc vẫn phải xác thực/ủy quyền theo design |
| **SID-T10** | Dùng token Kubernetes ở API không phải audience của nó | Không được chấp nhận như access token sai mục đích |
| **SID-T11** | Revoke identity/role hoặc tắt workload | Quyền mới và credential cũ được xử lý theo policy đã ghi |
| **SID-T12** | Rotate signing key/chứng chỉ | Credential mới hoạt động; credential cũ hết hiệu lực theo kế hoạch và limit đã duyệt |
| **SID-T13** | Role cloud IAM cấp đọc bucket B ngoài phạm vi | Effective permission hoặc request test phải từ chối |
| **SID-T14** | Log collector/issuer/STS không sẵn sàng | Có fail-safe/failure mode phù hợp, sự cố được phát hiện và escalated |
| **SID-T15** | Nâng cấp deployment và ServiceAccount binding | Danh tính đang chạy đúng principal/role, không tạo trust rộng ngoài ý muốn |

Bài test phải được thực hiện **được cấp phép**, tránh gửi credential thật vào log hoặc report. Khi thử negative access trên production, dùng identity/resource thử và bảo đảm không làm gián đoạn dịch vụ.

## 13. Vòng đời service identity và credential

Service identity không kết thúc khi token được cấp thành công. Nếu không có lifecycle, tài khoản cũ, role wildcard và credential chưa bị thu hồi sẽ tích tụ theo thời gian.

~~~mermaid
flowchart LR
    I["Đề nghị + chủ sở hữu + mục đích"] --> A["Approve và tạo principal"]
    A --> B["Gán workload và quyền tối thiểu"]
    B --> C["Cấp credential ngắn hạn"]
    C --> D["Sử dụng + authN/authZ + logging"]
    D --> E["Renew / rotate / monitor"]
    E --> D
    D --> R["Change / revoke / compromise"]
    R --> X["Thu hồi trust/permission và retest"]
    X --> Z["Decommission + hủy credential + evidence"]
~~~

### 13.1. Onboarding / enrollment

Cần xác nhận yêu cầu nghiệp vụ, system owner, môi trường, resource, hành động cần thiết, data classification và khả năng cấp identity trên nền tảng. Với CI job, phân biệt quyền **build/test** và quyền **ký/phát hành/deploy production**; cùng một runner không nên mặc định giữ mọi quyền.

### 13.2. Issuance và bootstrap

Quy định issuer, trust roots, identity mapping, key/cert management, token lifetime, audience, scope và attestation policy. Trong mô hình cần bảo vệ, credential nên có vòng đời ngắn và có thể được gia hạn an toàn; lifetime cụ thể do tổ chức xác định theo rủi ro và nền tảng.

### 13.3. Sử dụng và phân quyền

Dịch vụ nhận xác minh credential **ở trust boundary**, rồi kiểm tra action/resource/tenant; ghi các sự kiện bảo mật phù hợp mà không lưu raw token, secret hoặc nội dung không cần thiết.

### 13.4. Rotation và renewal

- Có thể **xoay khóa cấp token/chứng chỉ** hoặc **cấp lại credential workload**; hai hoạt động cần có kế hoạch tương ứng.
- Nêu thời gian overlap key, cách refresh JWKS/trust bundle và cách xử lý lỗi.
- Có phép test xác nhận **credential mới được chấp nhận** và **credential cũ bị từ chối khi hết hiệu lực** theo chính sách.
- Workload không giữ một bản token trong memory vô thời hạn khi file projected được rotate.
- Tránh chép credential vào image hoặc cấu hình không có cách hủy.

### 13.5. Revocation và sự cố

**Thu hồi IAM role** chưa chắc làm JWT bearer token đã phát hành mất hiệu lực ngay lập tức. Tùy công nghệ có thể cần token ngắn hạn, cơ chế introspection/revocation, thay trust/keys, ngắt network hoặc chặn principal. Các quyết định phải dựa vào kịch bản và capability thực tế, không hứa “revoke service account là mọi token vô dụng ngay” khi chưa kiểm chứng.

Khi credential lộ, cần phối hợp incident response: xác định phạm vi sử dụng, log, rotation, tài sản bị ảnh hưởng, thời gian token còn hiệu lực và các hành vi cần điều tra. Không ghi raw token vào incident evidence không được bảo vệ.

### 13.6. Decommission

Khi service bị xóa khỏi production, cần loại bỏ hoặc đóng ranh giới liên quan: Kubernetes ServiceAccount, IAM role/bindings, secret/key, policy trust, API client registrations, network access, backup/rotation jobs và CI permissions. Kiểm chứng principal cũ **không còn thực hiện action trái phép**. Một service đã tắt nhưng principal còn tồn tại là nguồn rủi ro tồn đọng.

## 14. Kiểm soát nguồn danh tính và CI/CD supply chain

Một workload có thể trình token chính xác nhưng vẫn đang chạy **mã ngoài ý muốn**. Khi đánh giá service identity, cần làm rõ quan hệ:

~~~text
Source/PR review
    -> Build + dependency checks
    -> Artifact provenance / image digest
    -> Approved deployment
    -> Runtime workload attributes
    -> Service identity / token issuance
    -> Resource-server authentication + authorization
~~~

Chỉ kiểm tra `serviceAccountName: export-worker` trong manifest không chứng minh **Pod được deploy từ artifact đáng tin**. Ngược lại, chỉ có image digest đã kiểm chứng không chứng minh quyền IAM và issuer mapping đang đúng.

### Các control liên quan

| Control | Mục tiêu | Evidence |
| --- | --- | --- |
| CI permission separation | Runner ít quyền không thể tự sửa production trust/identity | IAM CI effective permissions, negative tests |
| Artifact integrity | Deployment dùng artifact đã build/review theo quy trình | Build record, digest, deploy verification |
| Admission/runtime identity binding | Workload nhận đúng principal theo điều kiện được duyệt | ServiceAccount, cluster policy, runtime snapshot |
| Scoped issuer trust | Chỉ trusted issuer/subjects và audiences có quyền trao đổi token | STS trust config, mapping tests |
| Secret and token hygiene | Không phát tán credential qua code/log/image | Scan, code review, secret inventory |
| Change detection | Thay service identity/IAM/cert policy được phát hiện | Config drift, IAM change events, reviewer |
| Environment isolation | Identity non-prod không được phép hành động như production | Separate trust/role, deny tests |

Đặc biệt với **federation từ CI/CD**, claim như repository/branch/environment cần được kiểm tra theo **hợp đồng token thật của issuer**, không chỉ dựa vào tên pipeline do runner tự khai. Nếu token trust policy cho mọi branch nhưng cấp quyền deploy production, một thay đổi code bình thường có thể trở thành đường leo thang đặc quyền.

## 15. Security requirements và ma trận control có thể kiểm chứng

Để tránh kiểm tra hình thức, mỗi yêu cầu nên có **đối tượng, hành vi, phạm vi và bằng chứng**.

| ID | Security requirement | Control triển khai | Kiểm chứng/evidence |
| --- | --- | --- | --- |
| **SID-REQ-01** | Mọi workload production có principal/owner riêng theo phạm vi cần thiết | Service identity registry, workload binding | Inventory, owner, runtime SA/principal mapping |
| **SID-REQ-02** | Chỉ issuer/trust domain được phê duyệt được cấp identity có quyền cao | Issuer policy, attestation, STS trust | Trust policy review, negative issuance/federation test |
| **SID-REQ-03** | Resource API chỉ chấp nhận token đúng issuer, audience, lifetime, type và chữ ký | JWT/mTLS validation | Invalid/expired/wrong-audience negative tests |
| **SID-REQ-04** | Workload chỉ thực hiện action/resource theo quyền tối thiểu | IAM/resource policy, app policy | Effective IAM snapshots, positive/negative access |
| **SID-REQ-05** | Service gọi thay user vẫn phải bảo vệ quyền theo tenant và object | Business authorization, job ownership | Cross-tenant tests, queue/job mapping checks |
| **SID-REQ-06** | Credential không được tồn tại tĩnh, dùng chung hoặc rò ra theo chính sách áp dụng | Short-lived identity/secret control, scanning | Secret scan, workload runtime inspection, rotation evidence |
| **SID-REQ-07** | Thay identity/role/issuer phải kích hoạt kiểm tra và review | CI/IaC gate, change management, drift detection | Change ID, diff, reviewers, runtime retest |
| **SID-REQ-08** | Thu hồi/decommission hạn chế được quyền ngoài nhu cầu trong thời gian được phê duyệt | Revoke/rotation/lifecycle workflow | Negative test sau revoke, token expiry policy |
| **SID-REQ-09** | Sự kiện cấp, đổi, từ chối và sử dụng quyền đặc biệt có audit trail | Logging, correlation, monitoring | Synthetic event, collector/alert result |
| **SID-REQ-10** | Assessor có thể truy vết bằng chứng tới đúng service và deployment | Evidence register, artifact and policy refs | Signed-off assessment, deployment ID, limitations |

Không có một danh sách control duy nhất bắt buộc cho mọi kiến trúc. Mỗi yêu cầu cần điều chỉnh theo rủi ro, framework, quy định và cơ chế được phê duyệt; **thời gian giữ token hoặc tần suất review cụ thể** phải đến từ chính sách áp dụng.

## 16. Assurance case: risk → control → test → evidence

Một ví dụ cho worker có quyền đọc storage:

| Mắt xích | Nội dung |
| --- | --- |
| **RISK-SID-01** | Nếu worker bị chiếm hoặc token bị đánh cắp, quyền cloud rộng có thể cho đọc dữ liệu khách hàng ngoài phạm vi. |
| **OBJ-CONF-01** | Bảo vệ dữ liệu và giảm blast radius của một workload. |
| **SID-REQ-04** | Worker chỉ được đọc/ghi resource theo nhiệm vụ đã phê duyệt. |
| **CTRL-SID-01** | Gán principal riêng, cloud role scope tối thiểu và token workload ngắn hạn. |
| **SID-T13** | Thử quyền hợp lệ với bucket A, quyền trái phép với bucket B, kiểm tra policy hiệu lực. |
| **EV-SID-01** | STS trust snapshot, Kubernetes SA/pod binding, IAM policy, tests và deployment ID. |
| **FIND-SID-01** | Nếu role còn wildcard, không hạ residual risk chỉ vì federation đã được bật. |
| **RETEST-SID-01** | Thu hẹp quyền, đối chiếu runtime, test lại B bị từ chối và A vẫn hoạt động. |

### Mẫu YAML evidence register

Các giá trị trong dấu `<...>` là placeholder, không phải kết quả kiểm chứng thật:

~~~yaml
assessment_id: SID-ASSURANCE-001
module: SECURITY_SECURITY_ASSURANCE
claim_id: CLAIM-SID-01
risk_id: RISK-SID-01
requirement_ids: [SID-REQ-01, SID-REQ-02, SID-REQ-03, SID-REQ-04]
control_ids: [CTRL-SID-01]
environment: production
service: export-worker
workload_identity:
  principal_id: "<VERIFIED_PRINCIPAL_ID>"
  owner: "<SERVICE_OWNER>"
  runtime_binding: "<NAMESPACE_SERVICE_ACCOUNT_OR_INSTANCE>"
  issuer: "<TRUSTED_ISSUER>"
  audience: "<EXPECTED_AUDIENCE>"
  trust_policy_ref: "<STS_OR_ISSUER_POLICY_ID>"
resource_scope:
  - "<ALLOWED_BUCKET_OR_API>"
  - "<DENIED_RESOURCE_USED_IN_TEST>"
implementation:
  artifact_digest: "<CONTAINER_DIGEST>"
  deployment_id: "<ACTUAL_DEPLOYMENT>"
  iam_policy_ref: "<EFFECTIVE_IAM_SNAPSHOT>"
  secret_management_ref: "<CREDENTIAL_LIFECYCLE_POLICY>"
verification:
  assessed_at: "<ISO_8601_UTC>"
  test_ids: [SID-T01, SID-T03, SID-T04, SID-T07, SID-T13]
  test_report_ref: "<SANITIZED_POSITIVE_NEGATIVE_RESULTS>"
  issuer_rotation_test_ref: "<IF_APPLICABLE>"
  audit_event_ref: "<SYNTHETIC_EVENT_AND_COLLECTOR_TRACE>"
  result: "<PASS_FAIL_INCONCLUSIVE>"
  reviewer: "<AUTHORIZED_ASSESSOR>"
finding_refs: ["<FINDING_IF_ANY>"]
residual_risk: "<REVIEWED_RATIONALE_AND_DECISION>"
limitations: "<UNTESTED_CALL_PATHS_OR_IDENTITY_MAPPING>"
reassessment_triggers:
  - "Workload, ServiceAccount, issuer, IAM, ingress or artifact change"
  - "Security incident, unexpected token use or policy drift"
~~~

YAML chỉ là **chỉ mục**; các hiện vật phải tồn tại, có nguồn gốc, thời điểm, phiên bản, phạm vi và tính toàn vẹn phù hợp. Không thu thập raw access token hoặc private key vào hồ sơ để “chứng minh có danh tính”. Có thể lưu **token claim đã làm sạch, cấu hình trust, key ID không nhạy cảm và kết quả xác minh** với quyền truy cập được kiểm soát.

### Phân biệt design, implementation và operating effectiveness

| Loại bằng chứng | Trả lời | Không tự chứng minh |
| --- | --- | --- |
| **Design** | Danh tính dự định cấp cho workload nào? Role được thiết kế ra sao? | Policy đã deploy, runtime dùng đúng principal |
| **Implementation** | Manifest/IaC/code/pipeline có triển khai kiểm tra danh tính không? | Một phiên bản đang chạy thực tế không bị drift/bypass |
| **Runtime effectiveness** | Trong phạm vi test, token sai bị chặn, quyền ngoài scope bị từ chối? | Mọi tương lai, mọi region và mọi đường chưa test đã an toàn |
| **Governance** | Owner, approval, exception và lịch review có đầy đủ? | Credential đã được thu hồi hoặc quyền đã mất hiệu lực |
| **Incident evidence** | Có dấu sử dụng bất thường, timeline và phản ứng? | Không có log đồng nghĩa không có lạm dụng |

**Scope của claim không được vượt quá scope của evidence.** Test issuer/audience ở staging với test IdP không đủ để kết luận mọi production deployment đã kiểm tra đúng issuer/audience thật.

## 17. Đánh giá trạng thái và xử lý finding

Nên tách rõ những trạng thái:

- **PASS:** có bằng chứng đủ rằng requirement đạt trong phạm vi, thời điểm và môi trường đã đánh giá.
- **FAIL:** xác minh thấy sai (ví dụ token sai audience vẫn được chấp nhận; IAM còn quyền trái chính sách).
- **INCONCLUSIVE:** thiếu nguồn, thiếu quyền khảo sát, không kiểm tra được một route hoặc trạng thái runtime.
- **NOT_RUN / OVERDUE:** kiểm tra chưa diễn ra hoặc quá lịch; cần triage và review.
- **EXCEPTION_APPROVED:** người có thẩm quyền chấp nhận sai lệch/rủi ro trong điều kiện cụ thể, **không tự làm control trở thành PASS**.
- **REVOKE_PENDING:** đã quyết định thu hồi identity/role nhưng chưa chứng minh hành động đã có hiệu lực.

### Ví dụ remediation

**FIND-SID-01:** `export-worker` production đang dùng cloud role có quyền đọc mọi bucket, trong khi nhiệm vụ chỉ cần một prefix export.

1. Xác minh effective IAM permissions, các grant paths khác, workload binding và scope dữ liệu.
2. Phân tích impact và điều kiện lạm dụng; nếu đã có dấu compromise, chuyển incident response.
3. Đề xuất role giới hạn action/resource và các điều kiện phù hợp, review với Service/Data Owner.
4. Deploy thay đổi theo change management; xác minh workload đang dùng role mới.
5. Test **positive**: worker vẫn ghi/read tài nguyên cần thiết.
6. Test **negative**: thử quyền với bucket/tenant ngoài phạm vi bị từ chối.
7. Kiểm tra token/session còn hạn, credential cũ và service dùng chung role; ghi giới hạn.
8. Lưu test report, policy snapshot, deployment ID, reviewer và cập nhật residual risk.
9. Nếu có ngoại lệ, tách trạng thái gap và quyết định chấp nhận; xác lập hạn và trigger review.

Đóng ticket “đã đổi YAML” hoặc “đã liên kết ServiceAccount” mà không test **effective permission** là chưa đủ cho kết luận security assurance.

## 18. Trách nhiệm và quản trị danh tính không phải con người

| Vai trò | Trách nhiệm trọng tâm | Hiện vật thường cung cấp |
| --- | --- | --- |
| **Service / Tech Owner** | Định nghĩa workload, hành động cần thiết, dữ liệu, tenant và owner | Service inventory, data flow, trust boundaries |
| **Developer** | Không log credential, xây dựng authorization, negative tests, xử lý token renewal | Source/PR, test run, API authorization logic |
| **Ops / Platform / SRE** | Cấu hình Kubernetes SA, runtime identity, IAM, network, certificate, rotation và monitoring | Cluster/IAM snapshots, deployment, rotation records |
| **Identity / IAM Team** | Vận hành issuer/trust, federation policy, principal registry, key lifecycle | Issuer config, trust review, effective permission records |
| **Security / AppSec / SOC** | Threat model, đánh giá control, phát hiện mạo danh/sử dụng lạ và ứng cứu | Risk assessment, control testing, alert/timeline |
| **Data / Risk Owner** | Xác định tác động và thẩm quyền chấp nhận residual risk | Risk treatment, approval, exceptions |
| **Assessor / Audit** | Đối chiếu bằng chứng, phạm vi, hiệu lực và finding | Assessment result, retest, review trail |

Một ServiceAccount có thể được nhiều người vận hành tạo hoặc chỉnh. **Owner chịu trách nhiệm vòng đời** không nhất thiết là người đã gõ lệnh tạo account; khi nhân sự đổi nhóm cần handover và review các workload identities liên quan.

### Inventory trường tối thiểu

| Trường | Nội dung |
| --- | --- |
| Identity ID và loại | Workload principal, service account, SPIFFE ID, cloud role |
| Service owner / environment | Nhóm chịu trách nhiệm, cluster/namespace/region |
| Issuer / audience / credential type | Nguồn tin, bên nhận, TTL/rotation |
| Grant paths / effective permissions | Actions, resources, scope và điều kiện |
| Runtime binding | Deployment, Pod/VM/function, policy attestation |
| Data classification / purpose | Tài sản và lý do sử dụng quyền |
| Token/cert/secret lifecycle | Gia hạn, thu hồi, ngày review và xử lý sự cố |
| Evidence refs | Positive/negative tests, policy, deployment, log |
| Exceptions / findings | Sai lệch còn mở, hạn và thẩm quyền phê duyệt |
| Decommission status | Credential/grants/trust đã được dỡ và retest chưa |

**Không dùng “không có người đăng nhập” làm lý do miễn access review.** Non-human identities thường có quyền mạnh và cần được rà soát theo risk, nhất là những tài khoản CI/CD, backup, monitoring, KMS và production deployment.

## 19. Giám sát liên tục và trigger tái đánh giá

Service identity chịu tác động của release, thay đổi mạng, policy và vòng đời hệ thống. Một chương trình security assurance cần xử lý **drift và evidence freshness**.

| Trigger | Cần kiểm tra | Evidence |
| --- | --- | --- |
| Thêm worker/service hoặc namespace | Có owner, identity riêng và quyền cần thiết? | Inventory, SA/principal binding, access tests |
| Thay role IAM hoặc resource policy | Có cấp quyền ngoài phạm vi, đường gián tiếp? | Effective policy diff, deny tests |
| Thay issuer/JWKS/trust roots | Token nào được tin, rotation có an toàn? | Trust config, valid/invalid token tests |
| Thay CI runner/deployment/admission policy | Ai có thể lấy danh tính workload hoặc deploy mã? | CI IAM, provenance, runtime workload attributes |
| Thêm API/queue hoặc tenant | Caller policy có còn chính xác? | DFD, authorization negative tests |
| Token/secret bị lộ hoặc có anomaly | Đánh giá blast radius, revoke/rotate, điều tra timeline | Incident report, token usage/audit, revocation proof |
| Staging kết nối production | Có trust/secret/identity vượt môi trường? | Issuer mapping, policy tests |
| Issuer/STS hoặc log collector lỗi | Có fail-safe, detection và runbook được kiểm chứng? | Synthetic tests, alert delivery, outage evidence |
| Service được ngừng | Đã xóa role, credential, bindings và trust liên quan? | Decommission approval, deny tests |
| Audit finding / exception hết hạn | Control đạt chưa, residual risk cần quyết định lại? | Finding, remediation, retest, decision |

### Metrics và giới hạn diễn giải

Các chỉ số hữu ích: tỷ lệ workload có owner/principal riêng; quyền wildcard còn hiệu lực; số credential dài hạn hoặc dùng chung; số identity không hoạt động nhưng chưa decommission; tuổi credential và tỷ lệ rotation thành công; tỷ lệ service/role có positive-negative tests; số trust mapping quá rộng; số change chưa retest; time-to-revoke; detection coverage; số exception hết hạn.

Không diễn giải **“100% service có identity”** thành “100% access được bảo vệ”. Phải biết identity được cấp **đúng workload**, quyền có **least privilege**, token được **xác minh đúng audience** và hệ thống **không có đường bypass**. Một metric tốt nên đi kèm sample evidence và cảnh báo khi collector mất nguồn.

## 20. Case study: CI token và quyền production của export-worker

### Bối cảnh

Một nền tảng tài chính có:
- `report-api` xác thực user OIDC, nhận request xuất báo cáo.
- `export-worker` trên Kubernetes nhận job qua queue và tạo CSV.
- Một cloud storage chứa báo cáo nhiều tenant.
- CI/CD có quyền triển khai worker và thay ServiceAccount binding.
- Một workload identity federation đưa token ServiceAccount tới STS rồi nhận cloud credential.

Nhóm bảo mật phát hiện:
1. Federation trust policy tin mọi subject có prefix `system:serviceaccount:reporting:`, không phân biệt ServiceAccount cụ thể.
2. Role được cấp từ STS có `storage:*` trên nhiều bucket, kể cả production customer data.
3. Developer có thể tạo Pod mới trong namespace reporting và gán một ServiceAccount sử dụng cùng trust.
4. API nội bộ chỉ kiểm tra JWT signature và `exp`, chưa kiểm tra `aud`.
5. Một CI job in token dạng debug vào log trong một lần thất bại.
6. Security dashboard hiển thị “workload identity enabled – compliant”.

### Threat model và các lỗ hổng của claim

| Finding | Đường gây hại | Vì sao dashboard chưa đủ |
| --- | --- | --- |
| Trust subject quá rộng | Pod không được phê duyệt có thể trao đổi token lấy role mạnh | “Có federation” không chứng minh ai được cấp quyền |
| Role wildcard | Workload bị chiếm có thể truy xuất dữ liệu ngoài nhiệm vụ | Chỉ xác thực mạnh không giảm blast radius |
| Pod creation/RBAC rộng | Người/CI có quyền tạo workload có thể lấy danh tính nhạy cảm | Attestation theo SA chưa đủ khi quyền gán SA rộng |
| Bỏ kiểm tra `aud` | Token đúng chữ ký nhưng không dành cho API có thể bị dùng sai | Signature-only validation không bảo vệ token substitution |
| Token in CI log | Credential có thể bị đọc và phát lại trong cửa sổ hiệu lực | Phải điều tra, không dựa vào hạn ngắn để bỏ qua sự cố |

### Kế hoạch khắc phục theo thứ tự

1. **Điều tra và kiểm soát phơi lộ:** xác định log chứa token có thể bị ai đọc, thời hạn, audience, scope, dấu hiệu sử dụng; xử lý theo incident process khi có căn cứ.
2. **Chặn cấp identity sai:** thu hẹp trust mapping đúng issuer, audience, namespace, ServiceAccount và những điều kiện đã thẩm định.
3. **Giới hạn khả năng tạo workload:** review Kubernetes RBAC/admission, quyền deploy/CI và policy cho phép gán ServiceAccount.
4. **Thu hẹp quyền cloud:** thay role wildcard bằng actions/resources chính xác cho worker; xác minh **effective policy**.
5. **Cứng hóa resource server:** bổ sung issuer/audience/token-type checks và caller/resource authorization theo hợp đồng.
6. **Sửa quy trình log:** tránh in raw token, thu hồi/rotate theo khả năng, kiểm tra quyền log và thêm secret scanning.
7. **Kiểm thử và triển khai:** test hợp lệ, wrong-issuer/audience, unauthorized Pod subject, wrong bucket, cross-tenant job; đối chiếu deployment và trust thực tế.
8. **Đánh giá residual risk:** xác định các credential cũ còn hạn, đường bypass chưa test, khoảng log không có dữ liệu và owner chấp nhận theo thẩm quyền nếu cần.
9. **Giám sát liên tục:** alert khi role/trust mapping bị nới; review identity inventory và decommission.

### Kết quả assurance cần được viết cẩn trọng

**Không nên viết:** “Hệ thống an toàn vì dùng Kubernetes ServiceAccount và STS.”

**Có thể viết khi được kiểm chứng:** “Trong phạm vi `export-worker` production phiên bản được đánh giá, STS chỉ chấp nhận assertion từ workload subject/issuer/audience đã phê duyệt; quyền cloud hiệu lực chỉ cho phép hành động/tài nguyên theo policy; internal API từ chối token wrong-audience và job cross-tenant; bằng chứng test và runtime snapshot gắn với deployment ID. Các đường chưa đánh giá được liệt kê.”

Kết luận này vẫn phụ thuộc **trạng thái tại thời điểm và scope kiểm thử**, không bảo đảm vĩnh viễn sau một thay đổi IAM, issuer hoặc pipeline.

## 21. Bài thực hành

**Tình huống:** doanh nghiệp có ba service Java/Spring Boot: `orders-api`, `billing-worker` và `audit-service`. Các service giao tiếp qua REST và queue. Service chạy trên Kubernetes; một phần dữ liệu được ghi lên cloud storage. Có những đặc điểm:

- Hai service đang dùng chung ServiceAccount `default`.
- Một JWT access token dành cho `orders-api` được gửi sang `audit-service` và vẫn được chấp nhận.
- `billing-worker` có quyền đọc tất cả bucket dù chỉ cần ghi kết quả thanh toán vào một prefix.
- CI runner test có quyền đổi ServiceAccount mapping production.
- Log có những đoạn Authorization header để hỗ trợ debug.
- Một service cũ đã bị gỡ deployment nhưng OAuth client credential của nó vẫn hoạt động.

### Yêu cầu

1. Vẽ data flow và xác định trust boundary của từng luồng API, queue, identity issuer và storage.
2. Viết ít nhất **ba risk scenarios** có actor, điều kiện, action/resource, hậu quả và control còn thiếu.
3. Xác định các nguyên tắc thiết kế **identity riêng, issuer/audience và quyền tối thiểu** cho ba service.
4. Thiết kế tối thiểu **sáu negative tests**, trong đó có wrong audience, issuer, token expired, cross-tenant, storage outside prefix và ServiceAccount sai.
5. Phân biệt việc **revoke principal**, **revoke role**, **rotate signing key** và **token hết hạn**; đưa ra giới hạn của từng cơ chế.
6. Viết mẫu evidence record gồm principal, issuer, audience, runtime binding, deployment ID, IAM snapshot, test report, owner và reviewer.
7. Đề xuất cách xử lý sự cố token xuất hiện trong log, tránh làm mất bằng chứng nhưng không lưu/phát tán thêm raw token.
8. Xác định trigger đánh giá lại sau khi CI runner, issuer, storage policy hoặc ServiceAccount được thay đổi.

### Hướng giải mẫu

| Vấn đề | Đề xuất xử lý | Bằng chứng phải có |
| --- | --- | --- |
| Chung ServiceAccount | Tạo principal/binding riêng theo workload/nhu cầu | SA mapping runtime, deny policy, inventory |
| Token wrong-audience vẫn được nhận | Resource server xác minh `aud` theo API đích, `iss`, signature/lifetime | Positive + wrong-audience/wrong-issuer tests |
| IAM wildcard | Thu hẹp principal actions/resources và phân quyền theo prefix | Effective IAM policy, allowed/denied storage tests |
| CI có quyền đổi trust production | Tách quyền build/test/deploy, giới hạn phê duyệt và identity binding | CI IAM, workflow review, artifact/deployment evidence |
| Log Authorization header | Loại token khỏi log, review phạm vi lộ, rotate/revoke/điều tra | Sanitized incident timeline, code/config fix và regression tests |
| OAuth client của service cũ | Decommission client, credential, role và trust, test quyền không còn hoạt động | Revocation record và negative access test |

**Bài tập nâng cao:** Một service sử dụng X.509-SVID và mTLS đã xác thực thành công, nhưng API vẫn trả dữ liệu của mọi tenant vì service có role `GLOBAL_READER`. Tại sao đây không phải failure của mTLS mà vẫn là **failure của chương trình security assurance**? Hãy nêu control ở tầng policy/data, test cross-tenant và những bằng chứng chứng minh phạm vi quyền đã giảm.

## 22. Những sai lầm thường gặp

| Ngộ nhận | Vì sao sai? | Cách làm phù hợp |
| --- | --- | --- |
| “Service có tên DNS/hostname nên đã được xác thực.” | Tên gọi không phải credential được xác minh | Xác thực mTLS/JWT/issuer phù hợp và policy mapping |
| “Có JWT hợp lệ là được truy cập mọi API.” | Sai audience/scope/resource, token type hoặc quyền nghiệp vụ | Kiểm tra token validation và authorization độc lập |
| “Chỉ cần chữ ký JWT, bỏ kiểm tra audience.” | Token substitution/confused deputy | Xác thực đúng `iss`/`aud`/hạn/type theo contract |
| “Cùng cluster là an toàn, không cần auth nội bộ.” | Workload/credential nội bộ có thể bị chiếm | Identity per workload, network và app authorization |
| “ServiceAccount Kubernetes tự cấp quyền cloud đúng.” | Cloud trust và IAM mapping là cấu hình riêng | Xác minh federation policy và effective role |
| “Projected token ngắn hạn ngăn mọi replay.” | Bearer token bị lấy vẫn có thể được dùng trong hạn | Bảo vệ runtime token, scope nhỏ, detection, sender constraints nếu phù hợp |
| “SPIFFE/mTLS chứng minh image an toàn.” | Attestation identity không thay supply-chain integrity | Bảo vệ CI/admission/deploy và kiểm tra runtime |
| “Role có tên readonly luôn ít rủi ro.” | Đọc dữ liệu lớn có thể gây lộ nghiêm trọng | Xem action/resource/data classification |
| “Thu hồi quyền ở IdP làm token hết tác dụng tức thì.” | Token/cache/session và cách resource server xác minh khác nhau | Test thời gian thu hồi và thiết kế revocation phù hợp |
| “JWT scope đủ cho quyền của user gốc.” | Workload identity không thay kiểm tra tenant/object ownership | Context và policy cấp đối tượng |
| “Đã có IaC nên runtime đúng.” | Drift, bản deploy cũ, trust policy thay ngoài pipeline | Actual-state verification và negative tests |
| “Thấy authn failure alert là đủ audit.” | Có thể thiếu event thành công/đổi quyền, hoặc collector hỏng | Synthetic event, completeness và chain evidence |
| “Bài test ở staging chứng minh production an toàn.” | Issuer, secret, mạng, IAM, token policy có thể khác | Test theo đúng scope/deployment thực |
| “Workload decommission thì identity tự biến mất.” | IAM role/client credentials/trust có thể còn | Lifecycle inventory, revoke và retest |
| “Ngoại lệ được duyệt nghĩa là control PASS.” | Quyết định chịu residual risk khác hiệu lực kỹ thuật | Giữ FAIL/INCONCLUSIVE, approval và expiry riêng |

## Ghi nhớ

- **Service identity** xác định workload nào đang hành động; **credential** là phương tiện chứng minh identity, còn **authorization** quyết định nó được làm gì trên tài nguyên nào.
- Danh tính đáng tin cần **bootstrap/attestation, issuer và trust roots được quản trị, token/chứng chỉ giới hạn mục đích và vòng đời**; không chỉ đặt tên ServiceAccount.
- **JWT và mTLS** phải được kiểm chứng đúng trust context; JWT cần kiểm tra issuer, audience, signature, time và policy về token type; mTLS cần mapping peer identity tới quyền. Không cơ chế nào tự thay object/tenant authorization.
- **Kubernetes ServiceAccount, STS federation, SPIFFE/SPIRE và IAM** có những vai trò khác nhau; giảm key tĩnh không có nghĩa permission đã ít.
- Mọi service identity cần **owner, environment, scope, policy, credential lifecycle, rotation/revocation, decommission và evidence**; non-human accounts không được bỏ qua access review.
- Security assurance phải có **risk → requirements → controls → positive/negative tests → evidence → findings → remediation/retest**, cùng runtime verification theo đúng phiên bản.
- **Đánh giá liên tục** khi thay workload, CI, issuer, IAM, route, tenant, token policy hoặc sau sự cố; chưa có bằng chứng không tự động là PASS.

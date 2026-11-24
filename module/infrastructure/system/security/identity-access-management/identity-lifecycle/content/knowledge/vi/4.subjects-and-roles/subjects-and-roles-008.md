# Service account trong IAM: định danh dịch vụ, cấp quyền và quản lý vòng đời

Trong quản lý danh tính và truy cập (**Identity and Access Management – IAM**), không chỉ con người mới cần đăng nhập và được cấp quyền. Một ứng dụng tự động đồng bộ đơn hàng, tác vụ sao lưu chạy hằng đêm, công cụ triển khai hoặc dịch vụ đọc dữ liệu từ API đều cần một danh tính mà hệ thống đích có thể xác thực, phân quyền và kiểm toán. Một trong những cách thể hiện danh tính đó là **service account**.

Trong chương **Chủ thể và vai trò**, bài học này phân tích service account thuộc phạm vi **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**: cách định nghĩa và xác minh chủ thể phi con người, tạo tài khoản, cấp quyền, rà soát và thu hồi khi vai trò hay hệ thống thay đổi. Nội dung liên hệ mô hình **Joiner–Mover–Leaver (JML)** với IdP, SSO, SCIM, RBAC/ABAC, quản lý bí mật, kiểm toán và việc giảm **quyền truy cập tồn dư**.

## 1. Service account là gì?

**Service account** là một danh tính được cấp cho phần mềm, dịch vụ, tác vụ tự động hoặc thành phần hạ tầng để thực hiện những hành động cần thiết **thay cho một tiến trình**, không đại diện trực tiếp cho một nhân viên đang tương tác. Tên gọi và cơ chế triển khai khác nhau theo nền tảng: tài khoản trong hệ điều hành, danh tính máy trong cloud, service principal của một ứng dụng, hoặc tài khoản tích hợp tại một dịch vụ SaaS.

Ví dụ:

- Một job đồng bộ hàng tồn kho đọc cơ sở dữ liệu và gửi kết quả tới API ERP.
- Một dịch vụ thanh toán đọc bí mật kết nối từ secret manager rồi ghi bản ghi giao dịch trong phạm vi cho phép.
- CI/CD pipeline triển khai một phiên bản ứng dụng lên môi trường staging.
- Một tác vụ sao lưu lưu bản sao dữ liệu vào kho lưu trữ theo lịch.
- Một bộ kết nối SCIM sử dụng danh tính tích hợp để tạo, khóa và xóa tài khoản ở hệ thống đích.

Mỗi ví dụ đều cần trả lời năm câu hỏi: **Ai là chủ thể kỹ thuật? Ai sở hữu và phê duyệt? Chủ thể xác thực bằng gì? Nó được quyền làm gì trên tài nguyên nào? Khi nào quyền và credential bị thu hồi?**

Điểm quan trọng: **service account không phải là tài khoản nhân viên được chia sẻ mật khẩu**. Nếu tích hợp dùng tài khoản cá nhân của một kỹ sư, dịch vụ có thể ngừng chạy khi người đó nghỉ việc; ngược lại, để tài khoản cá nhân tồn tại chỉ để duy trì tích hợp tạo ra quyền truy cập tồn dư và khó kiểm toán.

## 2. Phân biệt các loại danh tính phi con người

Thuật ngữ **non-human identity (NHI)** bao quát nhiều loại danh tính. Service account là một cách cài đặt danh tính phi con người, nhưng không phải mọi NHI đều có một tài khoản lâu dài trong cơ sở dữ liệu người dùng.

| Khái niệm | Đại diện cho | Ví dụ | Lưu ý vòng đời |
| --- | --- | --- | --- |
| **Service account** | Dịch vụ hoặc tác vụ tự động | Tài khoản chuyên dụng cho backup job | Cần owner, credential, entitlement và quy trình thu hồi |
| **Service principal / application identity** | Ứng dụng đã đăng ký trong một hệ thống IAM | Client của API hoặc danh tính ứng dụng cloud | Gắn với ứng dụng, quyền, môi trường và tenant cụ thể |
| **Managed identity** | Danh tính workload do nền tảng quản lý credential | Compute instance đọc secret trong cloud | Nền tảng xử lý một phần vòng đời credential; vẫn phải quản trị quyền |
| **Federated workload identity** | Workload nhận token ngắn hạn qua quan hệ tin cậy giữa các bên | Pod hoặc pipeline trao đổi token với hệ thống cloud | Cần ràng buộc issuer, audience, subject và ngữ cảnh workload |
| **Machine/device identity** | Máy chủ, laptop hoặc thiết bị | Certificate của máy chủ để xác thực mTLS | Khác với quyền của những ứng dụng đang chạy trên máy |
| **Human account** | Một người cụ thể | Tài khoản SSO của nhân viên | Không nên dùng làm danh tính tích hợp chạy dài hạn |

Một máy chủ có thể có **device identity** riêng, đồng thời chạy nhiều ứng dụng, mỗi ứng dụng dùng **service identity** riêng. Không nên cho hai ứng dụng dùng chung một service account chỉ vì chúng nằm trên cùng máy hoặc cùng Kubernetes namespace.

Một service account cũng **không đồng nghĩa tài khoản đặc quyền**. Nhiều service account chỉ cần quyền đọc hoặc gửi thông điệp. Một số ít tài khoản cần quyền quản trị cao; với nhóm này phải tăng mức xác thực, phân tách nhiệm vụ, giới hạn thời gian và giám sát.

## 3. Mô hình dữ liệu: tách identity, credential, quyền và ownership

Thiết kế IAM nên phân biệt rõ:

1. **Identity:** định danh ổn định của chủ thể, chẳng hạn danh tính dịch vụ xử lý hóa đơn ở môi trường production.
2. **Credential:** phương tiện để chứng minh danh tính, ví dụ certificate, private key, client secret hoặc token do nền tảng cấp. Một identity có thể có nhiều credential đang dùng trong giai đoạn luân chuyển.
3. **Entitlement:** tập quyền được cấp; có thể là role, scope API, quyền IAM, quyền bảng dữ liệu hoặc ACL.
4. **Ownership:** đội/người chịu trách nhiệm và người phê duyệt quyền; đây là thông tin quản trị, không nhất thiết là subject sử dụng credential.
5. **Lifecycle state:** đang chờ phê duyệt, active, tạm khóa, cần xử lý sự cố, retired hoặc revoked.
6. **Runtime binding:** workload, môi trường triển khai, namespace, repository, job hoặc hạ tầng cụ thể được phép dùng identity.

Hồ sơ quản lý minh họa:

~~~yaml
serviceAccountId: svc-invoice-sync-prod
displayName: Invoice Synchronization
environment: production
ownerTeam: finance-platform
businessOwner: finance-operations
technicalOwner: platform-engineering
purpose: "Đồng bộ hóa đơn đã duyệt sang hệ thống kế toán"
runtime:
  type: kubernetes-workload
  namespace: invoice-prod
  workloadName: invoice-sync
authentication:
  method: federated-workload-identity
  issuerRef: trusted-cluster-issuer
authorization:
  roles:
    - invoice-approved-reader
    - accounting-event-publisher
  allowedEnvironment: production
lifecycle:
  state: ACTIVE
  reviewedAt: "2026-11-15"
  nextReviewAt: "2027-02-15"
~~~

Đây là **mô hình minh họa**, không phải schema cấu hình trực tiếp của IdP, cloud hoặc Kubernetes. Những trường như owner, mục đích sử dụng và ngày rà soát giúp phát hiện service account **mồ côi** khi hệ thống vẫn tồn tại nhưng không còn ai chịu trách nhiệm.

Không lưu giá trị client secret, private key hoặc access token vào hồ sơ inventory hay YAML đưa lên repository. Chỉ lưu tham chiếu đến hệ thống bí mật hoặc metadata như identifier, loại credential, hạn dùng và trạng thái.

## 4. Một request của service account được xác thực và phân quyền ra sao?

~~~mermaid
flowchart LR
    J["Scheduler / Workload"] --> I["Workload identity / credential"]
    I --> T["IdP / Token service"]
    T --> A["Access token có phạm vi"]
    A --> G["API Gateway / PEP"]
    G --> P["Policy Decision Point"]
    P --> G
    G --> R["Protected API / data"]
    O["Owner + IAM Governance"] --> P
    E["JML / deployment events"] --> O
    G --> L["Audit log"]
    T --> L
~~~

Luồng điển hình:

1. Workload khởi động trong môi trường đã đăng ký, lấy bằng chứng danh tính từ cơ chế đáng tin.
2. IdP, token service hoặc trust broker xác thực client/workload và cấp token phù hợp với dịch vụ đích.
3. Workload gửi access token hoặc thực hiện **mTLS** tới API.
4. Gateway/API xác minh issuer, audience, thời hạn, chữ ký hoặc kết quả introspection theo giao thức và trust configuration.
5. Điểm kiểm soát quyền (**Policy Enforcement Point – PEP**) áp quyết định từ chính sách **RBAC/ABAC**, bao gồm hành động và tài nguyên cụ thể.
6. Hệ thống ghi dấu vết về danh tính dịch vụ, workload, kết quả, tài nguyên và correlation ID.

**Authentication** trả lời *đây có đúng là service identity đã đăng ký không?* **Authorization** trả lời *identity đó có được thực hiện hành động này trên đúng tài nguyên, tenant và môi trường hiện tại không?*

Một access token hợp lệ không chứng minh rằng workload có quyền truy cập **mọi** bản ghi của API. Tương tự, một service account được gán role không có nghĩa request được chấp nhận nếu credential bị thu hồi hoặc tài khoản đã bị disable.

## 5. Các cách xác thực service account

| Cơ chế | Điểm mạnh | Rủi ro/công việc quản trị | Trường hợp sử dụng |
| --- | --- | --- | --- |
| **Managed identity / identity của nền tảng** | Nền tảng cấp bằng chứng ngắn hạn và quản lý nhiều khâu credential | Cần tin cậy đúng môi trường chạy, ràng buộc quyền tối thiểu và kiểm soát metadata/token endpoint | Cloud workload truy cập tài nguyên cùng môi trường hoặc được federation |
| **Workload identity federation** | Trao đổi bằng chứng workload lấy token ngắn hạn; tránh lưu cloud key dài hạn | Cần cấu hình đúng issuer, audience, subject, trust policy và giới hạn môi trường | Kubernetes, CI/CD, tích hợp đa cloud |
| **mTLS + certificate riêng** | Xác thực bằng sở hữu khóa riêng, phù hợp kênh dịch vụ đến dịch vụ | Quản lý CA, bảo vệ private key, cấp/gia hạn/thu hồi certificate | Service mesh, API gateway, hệ thống nội bộ |
| **OAuth 2.0 Client Credentials** | Chuẩn cấp access token cho client không có phiên người dùng | Phải bảo vệ cách client xác thực với authorization server; giới hạn scope/audience | Server-to-server API |
| **Client secret / API key tĩnh** | Tương thích hệ thống cũ, triển khai tương đối đơn giản | Dễ rò rỉ, khó quy trách nhiệm nếu dùng chung, cần secret manager và rotation | Chỉ khi tích hợp chưa hỗ trợ cơ chế mạnh hơn |
| **Username/password của tài khoản hệ thống** | Có thể cần cho hệ thống legacy | Mật khẩu dài hạn, khó MFA, dễ bị dùng như tài khoản người | Giới hạn riêng, giám sát và có lộ trình thay thế |

**Thứ tự ưu tiên thông thường:** dùng danh tính được nền tảng quản lý hoặc federation với token ngắn hạn khi phù hợp; dùng certificate/mTLS trong mô hình tương ứng; giới hạn API key hoặc mật khẩu tĩnh khi không có lựa chọn khác. Độ an toàn thực tế phụ thuộc cấu hình, khả năng bảo vệ credential và quyền được cấp, không chỉ tên công nghệ.

### OAuth 2.0 Client Credentials

Luồng **client credentials grant** cho phép client xác thực với authorization server và xin access token đại diện cho chính ứng dụng, không đại diện cho một nhân viên đăng nhập. Ví dụ minh họa:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=invoices.read
~~~

Ví dụ lược bỏ phần **xác thực client**: trong triển khai thật, authorization server còn cần xác thực client bằng phương thức đã đăng ký như client secret, private_key_jwt hoặc mTLS. Không được xem request trên là đầy đủ để tự cấp token.

Access token minh họa sau khi giải mã:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "svc-invoice-sync-prod",
  "aud": "invoice-api",
  "exp": 1790000000,
  "scope": "invoices.read"
}
~~~

Các trường trên chỉ mô tả ý nghĩa claim, **không phải một token có chữ ký hợp lệ**. Resource server cần xác minh token theo cấu hình giao thức, bao gồm issuer, audience, hạn dùng và chữ ký hoặc introspection. Chủ thể ở claim có thể được biểu diễn khác nhau giữa các IdP; không mặc định mọi hệ thống đều dùng cùng quy ước.

**OIDC** chủ yếu phục vụ xác thực danh tính người dùng trong nhiều luồng đăng nhập; **OAuth 2.0 Client Credentials** là cơ chế ủy quyền máy đến máy. Không sử dụng **ID token** thay cho **access token** để gọi protected API.

### Federation và giảm secret dài hạn

Với CI/CD pipeline hoặc workload Kubernetes, có thể dùng token do nền tảng chạy phát hành để **trao đổi** lấy credential ngắn hạn của cloud/API. Trust policy cần ràng buộc chặt chẽ các yếu tố tương ứng:

- **Issuer:** bên phát hành bằng chứng workload đáng tin.
- **Audience:** dịch vụ đích được phép nhận bằng chứng.
- **Subject/claims:** repository, branch, namespace, service account của workload, môi trường hoặc tên job được phép.
- **Lifetime:** thời hạn ngắn, không cấp token rộng hơn nhu cầu công việc.
- **Revocation:** có phương án vô hiệu hóa trust configuration hoặc workload khi bị xâm nhập.

Tránh trust policy quá rộng, ví dụ cho mọi repository hoặc mọi namespace trong một tổ chức đổi token để lấy đặc quyền production.

## 6. Phân quyền tối thiểu bằng RBAC và ABAC

Service account thường thực thi tự động và liên tục. Một quyền quá rộng có thể gây thiệt hại lớn hơn tài khoản chỉ đăng nhập ít lần. Vì thế cần xác định rõ **subject – action – resource – environment**.

| Quyền cần thiết | Quyền không nên mặc nhiên cấp |
| --- | --- |
| Đọc các hóa đơn đã được duyệt để đồng bộ | Quyền đọc mọi hóa đơn, kể cả bản nháp và dữ liệu lương |
| Gửi sự kiện tới một topic cụ thể | Quyền tạo/xóa mọi topic hoặc thay ACL |
| Đọc một secret cần cho tích hợp | Quyền liệt kê và đọc toàn bộ secrets trong tenant |
| Ghi bản backup vào một bucket theo prefix | Quyền xóa toàn bộ kho lưu trữ hoặc đổi cấu hình retention |
| Triển khai vào staging | Quyền triển khai hoặc truy cập secret production |

**RBAC** dùng vai trò có tập quyền xác định, ví dụ *invoice-reader*. **ABAC** bổ sung ràng buộc thuộc tính như environment, namespace, tenant, classification, chủ sở hữu tài nguyên hoặc thời gian được phép. Tùy hệ thống, có thể áp dụng policy dựa trên quan hệ hoặc điều kiện request.

Chính sách minh họa:

~~~yaml
policy: invoices.read-approved
effect: allow
subject:
  serviceAccountId: svc-invoice-sync-prod
  lifecycleState: ACTIVE
  environment: production
requiredRole: invoice-approved-reader
request:
  action: invoices.read
resource:
  tenantMatchesServiceTenant: true
  status: APPROVED
  classificationAtMost: INTERNAL
fallback: deny
~~~

Đây là **pseudoconfiguration**, không phải cú pháp của một công cụ policy cụ thể. Phải kiểm tra các thuộc tính từ nguồn đáng tin, không lấy role hoặc tenant do client tự nhập. Nếu thiếu hoặc không xác minh được thuộc tính bắt buộc, nên **deny by default**.

Khi cấp đặc quyền vận hành, áp dụng **separation of duties**: người yêu cầu, người phê duyệt, người phát hành credential và người kiểm toán nên có trách nhiệm được phân tách. Với tác vụ quản trị có thể dùng quyền cấp đúng lúc (**just-in-time**) thay cho quyền cao vĩnh viễn.

## 7. Vòng đời service account từ tạo đến thu hồi

Khác với tài khoản nhân viên, service account có thể tồn tại qua nhiều lần thay đổi người phụ trách. Vòng đời của nó thường gắn với **ứng dụng, workload, tích hợp hoặc hợp đồng cung cấp dịch vụ**.

~~~mermaid
flowchart LR
    R["REQUESTED / có nhu cầu"] --> A["APPROVED / owner xác nhận"]
    A --> P["PROVISIONED / cấp identity"]
    P --> U["ACTIVE / vận hành"]
    U --> V["REVIEW / rà soát và đổi quyền"]
    V --> U
    U --> Q["SUSPENDED / nghi sự cố"]
    Q --> U
    Q --> X["REVOKED / thu hồi"]
    U --> D["DECOMMISSIONING / dừng tích hợp"]
    D --> X
    X --> K["ARCHIVED / giữ bằng chứng"]
~~~

### Giai đoạn tạo mới

1. **Request:** ghi rõ nhu cầu nghiệp vụ, hệ thống nguồn/đích, môi trường, loại dữ liệu và thời hạn dự kiến.
2. **Ownership:** chỉ định technical owner, business owner và đội trực vận hành; xác định người phê duyệt các quyền nhạy cảm.
3. **Identity:** tạo định danh riêng cho mỗi workload hoặc use case có ranh giới bảo mật độc lập; không dùng tài khoản cá nhân và hạn chế tái sử dụng account chung.
4. **Authentication:** chọn managed identity, federation, certificate hoặc bí mật phù hợp; thiết lập chính sách TTL, rotation và điều kiện thu hồi.
5. **Authorization:** cấp scope và tài nguyên tối thiểu trong môi trường cần thiết; tránh quyền quản trị toàn cục.
6. **Runtime binding:** giới hạn workload/namespace/repository/host được phép sử dụng danh tính nếu nền tảng hỗ trợ.
7. **Audit/readback:** kiểm tra thử request hợp lệ và request ngoài quyền; lưu evidence về phê duyệt, quyền đã cấp và tài khoản đích.

### Giai đoạn vận hành

Mỗi service account cần có:

- Owner còn hiệu lực và **đường liên hệ khi sự cố**.
- Tập quyền thực tế, mục đích sử dụng, hệ thống đích và ngày rà soát.
- Theo dõi **last used** có giải thích, nhưng không mặc nhiên xóa account chỉ vì một khoảng thời gian im lặng: một số job chỉ chạy hàng tháng hoặc khi khôi phục thảm họa.
- Theo dõi credential sắp hết hạn, tài khoản bị khóa, lỗi xác thực, quyền thay đổi và khác biệt giữa cấu hình mong muốn với quyền thực tế.
- Phương án dự phòng cho việc tài khoản bị thu hồi khẩn cấp mà không mất dữ liệu hoặc làm gián đoạn công việc vượt mức cần thiết.

### Giai đoạn ngừng sử dụng

Trước khi xóa/tắt tài khoản, xác định các job, service, secret, cron, pipeline và ứng dụng đang phụ thuộc nó. Sau đó ngừng phát sinh công việc, thu hồi token/credential và role ở từng hệ thống đích, xác nhận không còn đường truy cập, xử lý dữ liệu và retention theo chính sách. Chỉ chuyển hồ sơ sang **archived/retired** sau khi có bằng chứng thu hồi.

## 8. Service account trong Joiner–Mover–Leaver

Sự kiện JML của con người tác động đến **ownership, quyền phê duyệt và khả năng tiếp cận secret**, nhưng không nhất thiết làm thay đổi danh tính của dịch vụ đang chạy.

| Sự kiện | Hành động với con người | Hành động với service account | Điều cần đối soát |
| --- | --- | --- | --- |
| **Joiner** | Cấp quyền cho nhân viên mới làm owner/operator sau phê duyệt | Thường giữ danh tính dịch vụ hiện hành; cập nhật danh sách người có quyền quản trị | Không tự động cho nhân viên mới xem tất cả secret của đội |
| **Mover** | Gỡ vai trò quản trị cũ, cấp vai trò mới | Đánh giá thay đổi owner, người phê duyệt, môi trường và đặc quyền của dịch vụ | Không giữ quyền sửa service account của đội cũ |
| **Leaver** | Khóa SSO/IdP, thu hồi phiên và quyền truy cập bí mật của nhân viên nghỉ | Chuyển owner; rotate các secret/key mà người đó biết hoặc đã truy cập khi rủi ro yêu cầu; giữ dịch vụ chạy an toàn | Không còn token cá nhân, quyền sửa cấu hình, tài khoản dự phòng hoặc credential bị lộ |
| **Ngừng workload** | Không nhất thiết có biến động nhân sự | Disable, revoke và deprovision danh tính dịch vụ, xóa quyền tài nguyên | Không còn credential sống, scheduler, quyền IAM hoặc account ứng dụng mồ côi |

### Ví dụ: người phụ trách tích hợp nghỉ việc

An là kỹ sư có quyền vận hành job đồng bộ thanh toán. Job chạy bằng danh tính **svc-payment-sync-prod** độc lập với tài khoản của An.

1. HR gửi sự kiện Leaver theo thời điểm có hiệu lực.
2. IAM khóa quyền SSO của An, thu hồi membership cho phép đọc secret, đổi policy của repository/CI/CD và xóa quyền phê duyệt.
3. Đội vận hành xác nhận owner mới cho **svc-payment-sync-prod**, kiểm tra lịch sử truy cập vault và loại credential An từng có thể xem hoặc sao chép.
4. Nếu dùng client secret tĩnh hoặc private key mà An biết, tiến hành rotation có kiểm soát; nếu dùng workload identity federation, kiểm tra An không còn khả năng sửa trust policy, deploy workload hoặc giả mạo nguồn phát hành.
5. Kiểm tra job tiếp tục hoạt động với danh tính kỹ thuật, role và credential mới; đối soát log xác nhận quyền của An đã hết hiệu lực.

**Không xóa service account chỉ vì owner nghỉ việc** nếu dịch vụ vẫn cần hoạt động. Tuy nhiên, cũng không để account không có owner hoặc để An giữ quyền gián tiếp qua repository, secret manager, máy chủ, tài khoản cloud hay token CI/CD.

### Ví dụ: Mover chuyển từ đội vận hành sang kiểm toán

Minh từng được quyền rotate certificate cho service account của Finance, sau đó chuyển sang bộ phận Kiểm toán. Quyền phù hợp với vai trò mới có thể là **chỉ đọc báo cáo kiểm toán**. IAM cần thu hồi role cấp secret/cấu hình, xóa membership của nhóm vận hành, cập nhật quy trình phê duyệt và kiểm tra các quyền ngoài IdP như API key cá nhân hoặc quyền cấp trong SaaS.

Nếu chỉ **thêm** quyền Kiểm toán mà không gỡ quyền vận hành cũ, Minh có thể vừa kiểm toán vừa sửa bằng chứng của hệ thống đang kiểm toán: một dạng xung đột nhiệm vụ.

## 9. Quản lý credential và luân chuyển an toàn

Credential dài hạn là điểm yếu thường gặp của service account. Các nguyên tắc cơ bản:

- Không lưu secret trong source code, file cấu hình public, ảnh container, tài liệu chia sẻ hoặc log.
- Dùng **secret manager/vault**, cấp quyền đọc theo đúng workload và môi trường; bật audit và giới hạn quyền chỉnh sửa.
- Ưu tiên **credential ngắn hạn** và federation khi nền tảng hỗ trợ.
- Nếu phải dùng secret tĩnh, có lịch rotation, cảnh báo hạn dùng, cơ chế thu hồi khẩn và đối soát nơi secret đã được phân phối.
- Không tái sử dụng cùng một secret ở dev, staging và production.
- Tách **quyền tạo credential**, **quyền đọc credential** và **quyền cấp quyền IAM** khi cần giảm xung đột nhiệm vụ.

### Quy trình rotation không làm gián đoạn

Với nhà cung cấp cho phép hai credential cùng tồn tại trong thời gian chuyển tiếp:

1. Xác minh inventory: tài khoản nào, hệ thống nào đang dùng secret/certificate cũ; kiểm tra owner và thời điểm bảo trì.
2. Tạo credential mới có phạm vi và thời hạn đúng, lưu vào vault; không ghi giá trị ra log.
3. Cập nhật cấu hình workload để lấy credential mới rồi triển khai tuần tự.
4. Xác minh đường truy cập hợp lệ và kiểm tra log xem credential cũ còn được dùng không.
5. Thu hồi credential cũ khi các consumer đã chuyển, ghi dấu thời điểm revoke và xác minh hệ thống đích từ chối nó.
6. Cập nhật inventory, lịch rotation, bằng chứng kiểm thử và cảnh báo liên quan.

Nếu nền tảng **không hỗ trợ** hai credential đồng thời, cần kế hoạch downtime/rollback phù hợp, tránh giữ secret cũ tồn tại vô hạn để phòng ngừa. Nếu credential bị lộ, ưu tiên **kiểm soát truy cập khẩn cấp và điều tra** thay vì tuân theo lịch rotation thông thường.

### Ví dụ lựa chọn phương thức

Một job chạy trên cloud có native managed identity thường không cần lưu client secret dài hạn. Một job chạy trong Kubernetes có thể sử dụng token danh tính workload ràng buộc service account của cluster để trao đổi lấy access token ngắn hạn. Với ứng dụng cũ chỉ hỗ trợ API key, phải lưu key trong vault, tách môi trường, hạn chế scope, rotate và theo dõi lần sử dụng cuối.

Việc chọn công nghệ không tự giải quyết vấn đề **quyền quá rộng**. Managed identity bị cấp quyền quản trị toàn tenant vẫn là rủi ro nghiêm trọng.

## 10. Liên hệ với IdP, SSO, SCIM và RBAC/ABAC

| Thành phần | Liên hệ với service account |
| --- | --- |
| **IdP / Authorization Server** | Có thể đăng ký application/client identity, xác thực client và phát hành token cho API |
| **SSO** | Chủ yếu phục vụ trải nghiệm đăng nhập của người dùng; service account thường không có phiên SSO tương tác |
| **OAuth 2.0** | Dùng access token và client credentials/federation tùy kiến trúc để ủy quyền machine-to-machine |
| **SCIM** | Đồng bộ tài khoản và nhóm ở ứng dụng hỗ trợ; không mặc nhiên quản lý mọi loại service identity hoặc rotate credential |
| **RBAC** | Gán quyền qua role chuyên dụng cho workload, ví dụ publisher của một event stream |
| **ABAC** | Hạn chế quyền theo tenant, environment, workload, nhãn tài nguyên, hành động hoặc ngữ cảnh |
| **IGA** | Quản trị yêu cầu, phê duyệt, ownership, rà soát định kỳ, phát hiện entitlement thừa và deprovision |
| **Secrets management / PKI** | Cấp, lưu, phát hành, rotate và revoke credential theo chính sách |

Nếu một bộ kết nối SCIM tự động tạo/khóa người dùng trong SaaS, **bộ kết nối cũng phải có danh tính kỹ thuật của riêng nó**. Quyền của connector có thể rất rộng, nên cần owner, cơ chế xác thực mạnh và phân tách môi trường. Việc nhân viên bị khóa ở IdP không tự động làm mất hiệu lực mọi API key của connector hoặc mọi local service account trong SaaS; phải có quy trình thu hồi và xác nhận ở từng đích.

## 11. Kiểm tra quyền ở ứng dụng: ví dụ Java

Giả sử một service account chỉ được đọc hóa đơn đã duyệt của tenant thuộc cấu hình tích hợp. Code minh họa ý tưởng:

~~~java
// Pseudocode: client identity được xây dựng từ token/mTLS đã xác thực.
Invoice getApprovedInvoice(TrustedServicePrincipal service, String invoiceId) {
    Invoice invoice = invoiceRepository.findById(invoiceId)
        .orElseThrow(ResourceNotFoundException::new);

    if (!service.isActive()) {
        throw new AccessDeniedException("service_account_inactive");
    }

    if (!service.hasScope("invoices.read")
            || !service.tenantId().equals(invoice.tenantId())
            || invoice.status() != InvoiceStatus.APPROVED
            || !policy.canReadInvoice(service, invoice)) {
        throw new AccessDeniedException("forbidden");
    }

    return invoice;
}
~~~

**Điều kiện tiên quyết**: cơ chế xác thực phía trước đã xác minh issuer, audience, hạn dùng, chữ ký/introspection hoặc chứng chỉ mTLS; đối tượng **TrustedServicePrincipal** được tạo từ kết quả đáng tin đó. Không xây dựng principal từ header như *X-Service-Account* hoặc trường body do client tự gửi.

Cách kiểm tra **scope + tenant + tình trạng tài nguyên** nhằm giảm lỗi ủy quyền mức đối tượng, kể cả khi token hợp lệ. Trong triển khai thực, nên lọc theo tenant ngay trong truy vấn dữ liệu và dùng policy engine/helper thống nhất để tránh bỏ sót một endpoint.

Các mã phản hồi thường gặp: **401 Unauthorized** khi request thiếu hoặc có credential không hợp lệ; **403 Forbidden** khi đã xác thực nhưng không đủ quyền. Một số API cố ý trả **404 Not Found** để tránh tiết lộ sự tồn tại của đối tượng.

## 12. Audit và kiểm toán quyền của service account

Log chỉ ghi “token issued” hoặc “request succeeded” là chưa đủ để chứng minh account còn cần thiết và được cấp đúng quyền. Nên phân biệt:

| Nhóm bằng chứng | Thông tin cần lưu | Câu hỏi có thể trả lời |
| --- | --- | --- |
| Tạo/đăng ký identity | Identity ID, purpose, owner, requester, approver, timestamp | Ai yêu cầu danh tính và vì sao? |
| Cấp/đổi entitlement | Identity, resource, role/scope, before/after, người phê duyệt, ticket | Ai cấp quyền nào, có vượt phạm vi không? |
| Phát hành/rotate credential | Credential reference, loại, hạn dùng, actor, thời điểm revoke | Credential cũ còn dùng được không? |
| Xác thực/token issuance | Client identity, issuer, method, kết quả, thời gian, request ID | Workload nào nhận token hoặc bị từ chối? |
| Quyết định truy cập | Service identity, action, resource scope, policy version, allow/deny | Vì sao một request được phép? |
| JML và deprovision | Owner trước/sau, nhóm/role đã gỡ, hệ thống đích, kết quả retry | Khi người phụ trách nghỉ việc, quyền còn lại ở đâu? |
| Rà soát định kỳ | Reviewer, danh sách quyền, quyết định giữ/gỡ, thời hạn ngoại lệ | Ai xác nhận quyền còn hợp lý? |

Không ghi **private key, secret, access token, refresh token** vào log. Có thể ghi ID token/event, hash hoặc dấu vết tham chiếu nếu đã đánh giá tác động bảo mật và quyền riêng tư. Cần thống nhất ID danh tính giữa IAM, vault, CI/CD và ứng dụng để điều tra xuyên hệ thống.

Các chỉ số quản trị hữu ích:

- **Orphan service accounts:** identity active nhưng không có owner còn hiệu lực.
- **Stale credentials:** credential hết hạn, không còn được sử dụng hoặc chưa rotation theo chính sách.
- **Overprivileged accounts:** quyền rộng hơn mục đích và thao tác thực tế.
- **Unused identities:** account không có hoạt động trong khoảng phù hợp với chu kỳ job, sau khi loại trừ tác vụ hiếm.
- **Revocation latency:** thời gian từ yêu cầu thu hồi đến lúc điểm thực thi xác nhận từ chối.
- **Review coverage:** tỷ lệ account đã được chủ sở hữu xác nhận entitlement trong kỳ.
- **Identity drift:** quyền thực tế khác với trạng thái mong muốn trong IAM/Infrastructure as Code.

Lưu ý: **không có activity** không tự động nghĩa là **không còn nhu cầu**; một tài khoản disaster recovery có thể được thiết kế chỉ dùng khi khẩn cấp. Phải kiểm tra purpose/owner và dependency trước khi thu hồi.

## 13. Xử lý service account bị lộ credential hoặc bị lạm dụng

Giả sử scanner phát hiện client secret của tài khoản triển khai production xuất hiện trong repository công khai. Các bước ở mức vận hành:

1. **Xác định phạm vi:** account, hệ thống đích, permission, credential đang lưu ở đâu, thời điểm có thể lộ.
2. **Chặn rủi ro ngay:** revoke hoặc vô hiệu hóa secret bị lộ theo phương án khẩn cấp; thu hồi token/phiên có thể thu hồi, hạn chế quyền account nếu cần.
3. **Bảo toàn bằng chứng:** ghi nhận sự kiện, bảo vệ log xác thực và quyết định quyền, kiểm tra hành vi bất thường từ lúc lộ.
4. **Cấp credential mới an toàn:** ưu tiên chuyển sang managed/federated identity; nếu vẫn cần secret, tạo mới trong vault và cập nhật consumer theo quy trình đã xác minh.
5. **Đánh giá tác động:** đối chiếu thao tác đã thực hiện, dữ liệu có thể bị truy cập hoặc sửa, và các tài khoản/token liên quan có khả năng bị lộ.
6. **Khắc phục nguyên nhân:** gỡ secret khỏi bản phân phối, cải thiện secret scanning, phân quyền repository, giảm scope và bật cảnh báo.
7. **Xác minh cuối:** credential cũ không còn sử dụng được tại API/IdP/hệ thống đích; account mới chỉ có quyền cần thiết.

Việc xóa secret khỏi commit hiện tại **không thu hồi** giá trị đã bị lộ trong Git history, log hoặc bản sao bên ngoài. Cần thay hoặc vô hiệu hóa secret tại hệ thống xác thực.

Trường hợp nghi vấn lạm dụng identity federation, cần kiểm tra **trust policy**, issuer, audience, subject matching, quyền triển khai workload và khả năng giả mạo token của nguồn phát hành. Không chỉ xóa một token ngắn hạn rồi bỏ qua cấu hình tin cậy rộng.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng tài khoản nhân viên để chạy job | Khi nhân viên nghỉ việc job dừng; nếu giữ tài khoản, tạo quyền tồn dư | Tạo danh tính dịch vụ độc lập, owner là vai trò quản trị |
| Một account dùng cho mọi dịch vụ/môi trường | Một lần lộ credential ảnh hưởng nhiều hệ thống, khó truy vết | Tách theo workload, ranh giới tin cậy và môi trường |
| Hardcode secret vào source code hoặc container image | Secret lộ qua repository/artifact/log | Secret manager, credential ngắn hạn và scanning |
| Cấp role administrator để “cho chạy được” | Rủi ro leo thang và truy cập sai tài nguyên | Quyền tối thiểu, kiểm thử yêu cầu cụ thể, policy review |
| Chỉ kiểm tra authentication, bỏ authorization | Token hợp lệ có thể đọc hoặc sửa tài nguyên ngoài nhiệm vụ | Kiểm tra scope, action, tenant, resource |
| Tạo service account không có owner | Không ai rà soát/rotate/revoke khi hệ thống thay đổi | Bắt buộc owner và quy trình chuyển giao |
| Chỉ tắt tài khoản trên IdP | API key địa phương, phiên hoặc quyền SaaS vẫn tồn tại | Inventory đa hệ thống và xác minh deprovision cuối đường |
| Xóa account ngay khi owner nghỉ việc | Dịch vụ vẫn cần hoạt động bị gián đoạn | Chuyển owner, rotate credential và rà soát quyền |
| Rotation nhưng không revoke credential cũ | Secret cũ vẫn sử dụng được sau ngày chuyển | Kiểm tra consumer, thu hồi, xác minh từ chối, cập nhật audit |
| Tin client ID tự khai là bằng chứng danh tính | Client giả danh account khác | Chỉ dùng principal từ xác thực mật mã/token đã xác minh |

## 15. Thiết kế tình huống thực tế: hệ thống sao lưu

Một ứng dụng muốn sao lưu dữ liệu lên object storage mỗi đêm. Hai phương án:

**Phương án A – không nên dùng:** job chạy bằng tài khoản cá nhân của quản trị viên; lấy mật khẩu qua biến môi trường trên máy build, có quyền quản trị tất cả bucket và tự ghi đè file bất kỳ.

**Phương án B – thiết kế có quản trị:** tạo danh tính **svc-backup-prod** gắn với workload backup, có owner và approval; lấy token ngắn hạn từ managed/federated identity; chỉ được ghi vào bucket đích, prefix cần thiết và không có quyền xóa toàn bộ bản backup. Log mỗi lần sao lưu với identity ID và request ID; đưa account vào lịch rà soát; khi ngừng hệ thống thì revoke danh tính và quyền đích.

### Ma trận quyền minh họa

| Hành động | svc-backup-prod | svc-backup-staging | Administrator người dùng |
| --- | --- | --- | --- |
| Ghi bản backup production vào prefix được định nghĩa | Allow | Deny | Theo quyền công việc được duyệt |
| Đọc backup production để phục hồi | Deny mặc định | Deny | Chỉ qua quy trình phục hồi được phê duyệt |
| Xóa hàng loạt bản backup | Deny | Deny | Giới hạn và cần bảo vệ đặc biệt |
| Ghi bản backup staging | Deny | Allow | Theo quyền được duyệt |
| Sửa trust policy của backup identity | Deny | Deny | Chỉ người quản trị được phân quyền, có kiểm toán |

Cách tách **quyền ghi** khỏi **quyền xóa/phục hồi** làm giảm hậu quả khi backup job bị chiếm quyền. Trong hệ thống thật, có thể bổ sung cơ chế chống sửa/xóa bản sao lưu (immutability, retention lock) theo khả năng nền tảng.

### Kiểm thử vận hành

1. Cho job chạy với identity hợp lệ, chứng minh ghi thành công vào đúng vị trí.
2. Thử ghi vào bucket hoặc tenant khác và xác nhận bị từ chối.
3. Thử xóa bản backup và xác nhận job không có quyền.
4. Thu hồi trust/credential thử nghiệm và xác nhận request mới không được phép.
5. Thay owner vận hành và xác minh quyền owner cũ bị gỡ nhưng lịch sao lưu vẫn hoạt động.
6. Ngừng thử workload và xác minh service identity, credential, permission và lịch chạy đều được xử lý.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Vì sao job tự động không nên chạy bằng tài khoản SSO cá nhân của kỹ sư?

**Trả lời:** Vì tài khoản cá nhân gắn với vòng đời nhân sự. Khi Mover/Leaver xảy ra, job có thể mất quyền hoặc tổ chức phải giữ tài khoản cá nhân không còn hợp lệ; cả hai đều gây vấn đề vận hành và kiểm toán. Nên có service identity riêng và owner được quản trị.

**Câu 2.** Managed identity hoặc workload federation có tự bảo đảm quyền tối thiểu không?

**Trả lời:** Không. Chúng chủ yếu giúp xác thực workload và giảm gánh nặng secret. Quyền IAM/role/scope, tenant và tài nguyên vẫn cần giới hạn và rà soát.

**Câu 3.** Nếu một service account có access token còn hạn nhưng bị gỡ quyền đọc invoice, API cần làm gì?

**Trả lời:** Thực thi quyền mới theo cơ chế policy hiện hành, xử lý cache/token theo SLA thu hồi, và từ chối hành động không còn được phép. Chỉ phát hành token ngắn hạn không đủ nếu điểm thực thi tiếp tục tin quyền cũ không giới hạn.

**Câu 4.** Một nhân viên nghỉ việc từng biết client secret của dịch vụ. Có cần xóa toàn bộ service account?

**Trả lời:** Không nhất thiết. Cần gỡ quyền của nhân viên, chỉ định owner mới, đánh giá phạm vi secret có thể lộ và rotate/revoke tương ứng; giữ dịch vụ hoạt động nếu còn nhu cầu hợp lệ.

**Câu 5.** Vì sao chỉ dựa vào danh sách service account “đã tạo” ở IdP chưa đủ để kiểm toán?

**Trả lời:** Cần biết quyền thực tế trên từng hệ thống đích, credential/phiên còn hiệu lực, owner, mục đích, lịch sử truy cập, kết quả thu hồi và các account/key ngoài luồng IdP.

---

**Ghi nhớ:** Service account là **chủ thể kỹ thuật có vòng đời, quyền hạn và người chịu trách nhiệm riêng**. Quản lý tốt đòi hỏi định danh rõ ràng, xác thực mạnh, phân quyền tối thiểu, credential ngắn hạn khi có thể, liên kết ownership với Joiner–Mover–Leaver và **đối soát thu hồi ở từng hệ thống đích**. Mục tiêu không chỉ là để tác vụ tự động chạy thành công mà còn bảo đảm mọi quyền đều có lý do, có người quản lý và có thể được thu hồi khi không còn cần thiết.

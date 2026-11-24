# Application identity trong IAM: định danh ứng dụng và quản lý vòng đời truy cập máy–máy

**Application identity** là danh tính được hệ thống nhận diện và sử dụng để **xác thực, cấp quyền và kiểm toán hành động của một ứng dụng hoặc thành phần phần mềm**. Khi một dịch vụ đồng bộ hóa gọi API, một job nền đọc dữ liệu từ object storage hoặc một bộ điều phối triển khai thay đổi tài nguyên cloud, đối tượng thực hiện hành động thường là **ứng dụng/workload**, không phải một nhân viên đang tương tác trực tiếp. Application identity giúp các hệ thống trả lời: **ứng dụng nào đang gọi, chạy ở đâu, thuộc ai, có thể làm gì, trong thời gian nào và ai chịu trách nhiệm khi cần thu hồi?**

Bài **“Application identity”** thuộc chương **Service identity**, module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi module là quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản, cấp quyền, rà soát đến thu hồi khi vai trò thay đổi. Với application identity, mô hình JML được áp dụng tương tự cho **onboard ứng dụng – thay đổi chủ sở hữu/nhiệm vụ – decommission**, kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và mục tiêu loại bỏ **quyền truy cập tồn dư**.

**Tình huống dẫn nhập:** Một ứng dụng báo cáo tên **report-worker** lấy dữ liệu thống kê từ Finance API mỗi đêm. Nhóm phát triển tạo một tài khoản nhân viên giả rồi lưu mật khẩu trong biến môi trường để job đăng nhập; API chấp nhận mọi dữ liệu của tenant. Khi người phụ trách rời công ty, không ai biết tài khoản đó thuộc ứng dụng nào, mật khẩu có thể đã bị sao chép và quyền vẫn tồn tại. Một thiết kế application identity đúng cần **principal riêng cho ứng dụng, nguồn tin cậy xác thực workload, phạm vi API tối thiểu, chủ sở hữu rõ ràng, credential có vòng đời, logging và thủ tục thu hồi kiểm chứng được**.

## 1. Application identity giải quyết vấn đề gì?

Trong kiến trúc phân tán, ứng dụng thường cần tương tác mà **không có người dùng trực tiếp**:

- Service A đọc cấu hình từ service B.
- API backend gọi ERP, CRM hoặc hệ thống thanh toán.
- CI/CD runner triển khai ứng dụng lên cluster production.
- Batch job đồng bộ báo cáo định kỳ.
- Workload trên Kubernetes truy cập cloud storage hoặc vault.
- SaaS integration cập nhật dữ liệu qua OAuth API.
- Automation bot thực hiện một workflow đã được phê duyệt.

Nếu mọi kết nối đều dùng **một account chung** hoặc dùng thông tin đăng nhập nhân viên, hệ thống khó biết **hành động xuất phát từ ứng dụng nào**, scope có đúng không, credential có cần thu hồi khi nhân sự rời tổ chức không, và sự cố lộ secret ảnh hưởng đến đâu.

### Lợi ích của application identity

| Mục tiêu | Cách application identity hỗ trợ |
| --- | --- |
| **Định danh rõ** | Mỗi ứng dụng/workload có principal được cấp và quản lý phù hợp. |
| **Xác thực đúng đối tượng** | Dựa trên client authentication, workload attestation, managed identity, mTLS hoặc federation. |
| **Ủy quyền tối thiểu** | Chỉ cho action/resource/tenant cần thiết; không lấy role admin mặc định. |
| **Truy vết** | Gắn API call với client/principal, owner, môi trường và correlation ID. |
| **Quản lý vòng đời** | Onboard, thay đổi scope/owner, rotate credential, revoke, decommission. |
| **Độc lập với tài khoản con người** | Nhân viên Mover/Leaver không bắt buộc làm dừng service đang hoạt động hợp lệ. |
| **Giảm quyền tồn dư** | Thu hồi client grants, credentials, service accounts và các đường trust không còn dùng. |

**Application identity không tự làm ứng dụng đáng tin.** Một workload hợp lệ vẫn có thể bị khai thác hoặc bị cấu hình quá quyền. Cần kết hợp **bảo vệ credential, least privilege, token validation, resource-level authorization và monitoring**.

## 2. Phân biệt application identity, service account và user identity

Các thuật ngữ thường gần nhau nhưng không luôn tương đương giữa các nhà cung cấp.

| Thuật ngữ | Định nghĩa thực dụng | Ví dụ |
| --- | --- | --- |
| **Human/user identity** | Danh tính của một người được xác minh qua IdP, SSO, MFA hoặc cơ chế phù hợp. | Nhân viên đọc hóa đơn trên trình duyệt. |
| **Application identity** | Danh tính đại diện cho ứng dụng khi xác thực/truy cập hệ thống. | Client của report-worker gọi Finance API. |
| **Workload identity** | Danh tính ràng buộc với workload/runtime thực thi, thường được cấp ngắn hạn. | Pod Kubernetes dùng OIDC federation để lấy cloud token. |
| **Service account** | Tài khoản phi con người dành cho dịch vụ hoặc automation, tùy nền tảng. | Kubernetes ServiceAccount; cloud service account; account kỹ thuật của SaaS. |
| **Service principal** | Đối tượng danh tính/quyền đại diện ứng dụng trong một môi trường identity cụ thể. | Principal ứng dụng được tạo trong tenant identity. |
| **OAuth client** | Thực thể đã đăng ký với Authorization Server để dùng các OAuth flows. | Confidential client dùng client credentials. |
| **App registration** | Cấu hình đăng ký ứng dụng: client_id, redirect URI, credentials hoặc trust. | Application registration trong IdP. |
| **Machine identity** | Thuật ngữ rộng cho danh tính máy, service, thiết bị và workload. | Certificate identity của một service. |

**Không có ánh xạ 1:1 toàn cục** giữa các thuật ngữ. Một ứng dụng có thể có **một registration nhưng nhiều service principals** ở những tenant; một service được triển khai ở staging/production có thể dùng **hai workload identities tách biệt**; một ứng dụng dùng nhiều OAuth clients cho các môi trường độc lập.

### Human và application identity có thể cùng xuất hiện

Một người dùng đăng nhập Finance Portal bằng SSO, rồi Finance Portal gọi báo cáo ở API khác:

- **Human identity** trả lời người dùng là ai.
- **Application identity** trả lời ứng dụng/trung gian nào thực hiện lời gọi.
- **Delegation/authorization context** trả lời ứng dụng có đang hành động thay người dùng hay hoàn toàn bằng quyền của chính ứng dụng.

**Không gộp mọi request của ứng dụng thành quyền của user, và cũng không tự suy rằng ứng dụng có quyền thay mọi user**.

## 3. Những thành phần cần phân biệt trong hệ thống IAM

| Thành phần | Vai trò | Điều không được suy ra |
| --- | --- | --- |
| **Application registration** | Metadata định danh client và các thiết lập bảo mật. | Registration tự động có quyền đọc mọi API. |
| **Client ID** | Định danh công khai của OAuth client. | Client ID là bí mật hoặc đủ chứng minh danh tính. |
| **Client credential** | Cách confidential client xác thực với AS. | Credential có nghĩa ứng dụng được phép làm mọi hành động. |
| **Service principal / target principal** | Danh tính ứng dụng trong hệ thống ủy quyền cụ thể. | Principal ở tenant A mặc nhiên được tenant B tin. |
| **Authorization Server (AS)** | Xác thực client và cấp token theo policy/grant. | Token được cấp hợp lệ cho mọi Resource Server. |
| **Resource Server (RS)** | API/dịch vụ bảo vệ tài nguyên. | Một scope luôn đủ cho mọi business action. |
| **Policy Enforcement Point (PEP)** | Chặn/cho truy cập tại endpoint/tài nguyên. | Mọi endpoint, batch worker đã dùng cùng kiểm soát. |
| **Policy/Entitlement Catalog** | Xác định permissions, app roles, resource scopes. | Tên role mô tả đầy đủ effective access. |
| **Workload identity provider / attestation** | Liên kết workload runtime với một principal. | Mọi workload chạy trong cluster đều có cùng trust. |
| **Audit & Inventory** | Ghi danh tính, grants, owner, usage và sự kiện. | Có log là ứng dụng đã được cấp quyền tối thiểu. |

### Service principal không phải credential

Principal là **thực thể được gắn quyền**; credential hoặc cơ chế federation là **cách xác thực danh tính đó**. Xoay vòng một secret không nhất thiết thay principal ID; thu hồi một permission không nhất thiết làm secret hết hiệu lực; xóa app registration có thể có tác động khác tùy provider.

Do đó quản lý vòng đời phải tách **identity lifecycle**, **credential lifecycle** và **authorization/grant lifecycle**, rồi xác minh trạng thái cuối ở target.

## 4. Các sơ đồ tương tác căn bản

### 4.1 Máy–máy không có người dùng

~~~mermaid
sequenceDiagram
    participant W as Report Worker
    participant AS as Authorization Server
    participant RS as Finance API / Resource Server
    participant P as IAM Policy & Attribute Source
    W->>AS: Xác thực client/workload + xin token
    AS->>P: Kiểm trust, grant, policy, audience
    P-->>AS: Quyết định và scope hợp lệ
    AS-->>W: Access token có audience/scope phù hợp
    W->>RS: API request + access token
    RS->>RS: Kiểm issuer, signature/keys, exp, audience...
    RS->>P: Kiểm principal, action, tenant, resource
    P-->>RS: ALLOW / DENY
    RS-->>W: Phản hồi theo quyền được phép
~~~

**Không được mặc nhiên thay Authorization Server bằng Resource Server**. Nhận được token từ AS chỉ chứng minh quá trình cấp token đạt điều kiện nào đó; RS vẫn phải kiểm token **dành cho chính nó** và policy nghiệp vụ của request.

### 4.2 Người dùng + ứng dụng trung gian

~~~mermaid
flowchart LR
    U["Người dùng đã xác thực"] --> WEB["Web App / Client"]
    WEB --> API["Backend API"]
    API --> D{"Bối cảnh truy cập?"}
    D -->|Delegated| DE["Token/authorization mang quyền ủy nhiệm hợp lệ"]
    D -->|App-only| AO["Application identity và app permissions"]
    DE --> RS["Downstream Resource Server"]
    AO --> RS
    RS --> A["Kiểm subject/client, scope, tenant, resource"]
~~~

**Delegated access** và **application-only access** không được nhập nhằng. Một ứng dụng có quyền app-only rộng có thể bỏ qua giới hạn của user nếu backend chọn sai token hoặc không ràng buộc tài nguyên.

## 5. Các mô hình sử dụng application identity

| Mô hình | Chủ thể thực thi | Phương thức thường thấy | Nguy cơ chính |
| --- | --- | --- | --- |
| **Backend-to-backend** | Service A gọi Service B. | OAuth client credentials, mTLS hoặc workload identity. | Token audience rộng, app role quá mức. |
| **Scheduled job** | Job chạy không có user. | Managed identity hoặc client credential. | Credential dài hạn, owner biến mất, cron bỏ quên. |
| **Cloud automation** | IaC, CI/CD, serverless function. | Workload federation, role binding/assume-role. | Trust policy mở rộng, quyền production wildcard. |
| **SaaS integration** | Connector với CRM/ERP. | OAuth application permissions hoặc API key. | Consent quá rộng, token tồn dư sau gỡ integration. |
| **Human delegated app** | Web app hành động theo user. | Authorization code + PKCE, downstream OBO/token exchange khi hỗ trợ. | Nhầm user permissions với app permissions, token forwarding sai. |
| **Kubernetes workload** | Pod/Job với ServiceAccount. | Bound projected token / external federation / mesh mTLS. | Dùng chung SA, token mount quá rộng, sai audience. |
| **Emergency automation** | Recovery controller. | Credential/role break-glass có điều kiện. | Standing high privilege và thiếu audit độc lập. |

Một application có thể kết hợp nhiều mô hình. Phải xác định **identity, trust boundary, authorization type và owner** cho từng luồng thay vì cấp một service principal toàn quyền cho mọi chức năng.

## 6. Application identity trong OAuth 2.x: client và quyền ứng dụng

OAuth là framework ủy quyền; không phải mọi flow đều tương đương hoặc dùng cho xác thực người dùng. Với ứng dụng máy–máy, **Client Credentials Grant** là một lựa chọn phổ biến **khi confidential client có thể xác thực với AS và được cấp quyền app-only**.

### Ví dụ yêu cầu token dạng khái niệm

~~~http
POST /oauth2/token HTTP/1.1
Host: idp.example.internal
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=reports.read
~~~

Credential xác thực client **không được hiển thị trong ví dụ**; AS có thể yêu cầu mTLS, private_key_jwt, client secret hoặc phương pháp khác tùy hợp đồng. Endpoint, scope và phương thức xác thực thực tế là của deployment, không phải mặc định chung.

### Token cần được hiểu đúng

Một access token dạng JWT có thể chứa các claims như:

~~~json
{
  "iss": "https://idp.example.internal",
  "sub": "app-report-worker",
  "aud": "finance-api",
  "client_id": "report-worker",
  "scope": "reports.read",
  "iat": 1795420000,
  "exp": 1795420600
}
~~~

**Cấu trúc claims chỉ minh họa**. Không phải mọi access token là JWT, không phải provider nào cũng dùng claim giống nhau; JWT access-token profile có những quy tắc riêng. Ngữ nghĩa của **sub, client_id, appid, roles, scp, azp** phải theo **issuer contract**, không áp quy tắc của vendor này lên vendor khác.

Resource Server cần kiểm theo triển khai:

1. Token được nhận từ **issuer tin cậy**, không nhận token do client tự ký.
2. Chữ ký/khóa/JWKS hoặc introspection hợp lệ, cùng **thuật toán được cho phép**.
3. **Audience** phù hợp API đích; token dành cho API A không được dùng ở API B.
4. Các giới hạn thời gian **exp, nbf** nếu có, cùng sai số đồng hồ được kiểm soát.
5. **Client/principal** được xác định từ claims/response đáng tin.
6. **Scope/app role** phù hợp action và **resource/tenant authorization** ở backend.
7. Account/application grant còn đáp ứng điều kiện hiện hành nếu policy yêu cầu thu hồi nhanh.
8. Context bổ sung như sender constraint, workload identity, network hoặc risk theo quy định.

**Client ID không phải mật khẩu**, và **OIDC ID token không thay thế access token để gọi API**.

## 7. Client Credentials và delegated access không được đánh đồng

| Tiêu chí | App-only / Client Credentials | Delegated user access |
| --- | --- | --- |
| Có user đang hiện diện? | Không bắt buộc. | Có quyền được ủy nhiệm từ user theo flow thích hợp. |
| Quyền phụ thuộc vào | Application grants, service principal, policy. | Quyền user, client và resource server policy theo mô hình. |
| Khi user Leaver | Không nhất thiết ngừng app-only job; phải xét owner và business need. | User-delegated token/grants thường cần bị xử lý theo lifecycle/user policy. |
| Audit | App/client/workload là principal tác động. | Cần xác định user và client, đôi khi OBO chain. |
| Rủi ro | App permissions quá rộng/credential lộ. | Consent quá rộng, token forwarding, nhầm actor. |
| Ví dụ | Job tổng hợp dữ liệu mỗi đêm. | Web app đọc hồ sơ thay user đăng nhập. |

### On-behalf-of (OBO) và token exchange

Một backend có thể cần gọi API B **thay user đã đăng nhập**. Những cơ chế như OBO/token exchange (nếu AS/RS hỗ trợ) cần bảo toàn **user identity, client identity, audience, scopes và trust** theo contract. **Không chuyển tiếp nguyên một access token của API A sang API B** nếu audience không khớp; điều này tạo nguy cơ token confusion và confused deputy.

### Nếu ứng dụng dùng app-only để phục vụ yêu cầu user

Khi backend dùng **app-only permission** rộng để xử lý request do user gửi, nó vẫn phải **tự kiểm user authorization trên tài nguyên trước khi gọi downstream API**. Quyền app-only không được trở thành con đường vượt qua giới hạn RBAC/ABAC của user.

## 8. Các cách xác thực application identity

| Phương pháp | Nguyên tắc | Ưu điểm | Cảnh báo |
| --- | --- | --- | --- |
| **Client secret** | App trình secret để xác thực với AS. | Triển khai rộng, tương thích nhiều hệ thống. | Secret có thể bị sao chép; lưu trong source/log là rủi ro cao. |
| **private_key_jwt** | App chứng minh quyền sở hữu private key bằng assertion ký số. | Không gửi shared secret, hỗ trợ key rotation. | Private key phải được bảo vệ; JWT validation và key lifecycle đúng. |
| **Mutual TLS (mTLS)** | Hai đầu xác thực bằng chứng thư theo trust configuration. | Xác thực client bằng certificate, có thể hỗ trợ sender-constrained token. | PKI, expiry, SAN mapping, revocation và TLS termination phức tạp. |
| **Managed identity** | Nền tảng cung cấp identity/token cho workload đủ điều kiện. | Giảm nhu cầu tự lưu secret dài hạn. | Phải bảo vệ runtime, principal bindings và metadata/token endpoints. |
| **Workload identity federation** | AS tin một workload attestation/assertion của issuer bên ngoài theo điều kiện. | Có thể trao token ngắn hạn, giảm static secrets. | Phải ràng buộc chặt **issuer, subject, audience, repo/namespace/environment**. |
| **Platform service account** | Runtime gắn danh tính vào pod/job/service. | Định danh workload theo namespace và runtime. | Không mặc định có quyền cloud/API; cần trust và authorization rõ. |
| **API key** | Chuỗi bí mật định danh/tùy implementation xác thực client. | Dễ tích hợp với legacy. | Thường có giới hạn về expiry/scope/rotation; cần đánh giá bảo mật. |

**Secretless** là mục tiêu giảm secret tĩnh cần quản lý trực tiếp, **không có nghĩa workload không có credential/token**. Managed identity hoặc federation vẫn có short-lived tokens, trust bindings và khả năng bị lạm dụng nếu runtime hoặc policy bị chiếm.

## 9. Workload identity federation: tin đúng workload, không tin mọi runner

Khi một CI/CD job hoặc một pod cần token để gọi Cloud API, mô hình liên kết danh tính có thể dùng **assertion ngắn hạn** từ một issuer được tin cậy, thay vì lưu client secret có thời hạn dài.

~~~mermaid
sequenceDiagram
    participant W as Workload / CI Job
    participant I as Trusted Workload Issuer
    participant AS as Cloud STS / Authorization Server
    participant R as Cloud Resource / API
    W->>I: Yêu cầu workload assertion theo runtime identity
    I-->>W: Signed assertion với iss, sub, aud, exp
    W->>AS: Exchange assertion + requested audience/scope
    AS->>AS: Verify issuer, signature, subject binding, audience, expiry
    AS->>AS: Evaluate trust policy + authorized role/scope
    AS-->>W: Short-lived access credential/token
    W->>R: API request với credential/token
    R->>R: Verify token và resource-level authorization
    R-->>W: ALLOW hoặc DENY
~~~

**Không mặc định một assertion OIDC có thể được dùng làm access token tại API đích**. Thường cần bước token exchange/security token service theo provider contract; audience và token type phải được kiểm đúng.

### Thành phần của trust binding

| Thành phần | Ví dụ khái niệm | Nguy cơ khi quá rộng |
| --- | --- | --- |
| **Issuer (iss)** | Issuer của cluster hoặc CI provider được duyệt. | Tin token từ issuer khác ngoài tổ chức. |
| **Subject (sub)** | Workload/service account cụ thể. | Trust mọi repo, project hoặc namespace. |
| **Audience (aud)** | Mục đích trao đổi token dành cho cloud STS. | Token của audience khác bị tái sử dụng. |
| **Namespace/repository** | Tên namespace, repo và project identity. | Staging job có thể dùng production role. |
| **Branch/environment/ref** | Production deployment environment được bảo vệ. | Pull request không được kiểm có thể assume role production. |
| **Token TTL** | Thời gian assertion/credential hữu hạn. | Token tồn dư lâu sau decommission. |
| **Role binding** | Action/resource cloud đã duyệt. | Wildcard admin rộng hơn nhu cầu. |

**Trust policy và permission policy là hai cổng độc lập**: trust quyết định **ai có thể nhận/assume role**, còn permission policy quyết định **role làm được gì**. Một role ít quyền nhưng trust mở cho bất kỳ repository cũng tạo rủi ro; một trust chặt nhưng role global admin vẫn có blast radius lớn.

### Điều kiện vận hành quan trọng

Tránh dùng một subject pattern quá rộng như mọi workload trong một namespace hoặc mọi branch nếu chỉ production deploy mới cần quyền. Khi đổi repository, service account name hoặc issuer, cần **re-evaluate trust binding** và **thu hồi ràng buộc cũ** để không tồn tại hai đường assume-role ngoài ý muốn.

## 10. Kubernetes ServiceAccount và danh tính workload

Trong Kubernetes, một **ServiceAccount** là đối tượng API trong namespace có thể gắn vào pod. Đây không đồng nghĩa với OAuth client, IdP user hoặc cloud service account theo mọi nghĩa:

- Pod có thể sử dụng **projected, bound ServiceAccount token** có audience và expiry phù hợp.
- Kubernetes RBAC cấp quyền gọi **Kubernetes API** cho ServiceAccount; không tự mở quyền Finance API hoặc cloud account.
- Khi federation ra cloud, bên nhận cần có **trust binding** cho issuer/subject/audience thích hợp.
- Workload có thể cần thêm **mTLS service identity** trong service mesh hoặc SPIFFE/SPIRE nếu triển khai.
- Tách **dev, staging, production** bằng ServiceAccounts và permissions khác nhau nếu mức rủi ro khác nhau.

### Ví dụ khai báo ServiceAccount

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: invoice-reader
  namespace: finance-prod
automountServiceAccountToken: false
~~~

Đây là tài nguyên ví dụ; **automountServiceAccountToken: false** ngăn tự động mount token ServiceAccount mặc định vào pod, không tạo sẵn federation. Nếu workload cần token để federation, phải cấu hình **projected token có audience/expiration phù hợp**, mount có chủ đích và trust policy của bên nhận. Không bật tự động token mount chỉ vì thuận tiện.

### Ví dụ Pod dùng projected token (minh họa)

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: invoice-job
  namespace: finance-prod
spec:
  serviceAccountName: invoice-reader
  automountServiceAccountToken: false
  containers:
    - name: worker
      image: registry.example.internal/invoice-worker:1.0.0
      volumeMounts:
        - name: federation-token
          mountPath: /var/run/workload-identity
          readOnly: true
  volumes:
    - name: federation-token
      projected:
        sources:
          - serviceAccountToken:
              path: token
              expirationSeconds: 3600
              audience: finance-token-exchange
~~~

Đây là **khai báo minh họa**, không phải cấu hình có thể triển khai an toàn nguyên trạng. Cần bổ sung resource limits, image provenance, admission/security controls, policy network, runtime hardening và cấu hình issuer/token exchange tương ứng. **Audience** phải khớp bên chấp nhận token, không lấy từ tên bất kỳ mà thiếu trust contract.

### SPIFFE/SPIRE và service identity dựa trên certificate

Một kiến trúc khác có thể dùng **SPIFFE ID** và X.509 SVID/JWT-SVID do hệ thống đáng tin cấp để định danh workload. Đây là **lựa chọn thiết kế**, không phải yêu cầu bắt buộc của OAuth hay Kubernetes. Cần bảo vệ workload attestation, trust domain, vòng đời chứng thư và chính sách authorization ở API; **mTLS xác thực danh tính peer không tự định nghĩa quyền nghiệp vụ**.

## 11. App registration, service principal và phân tách môi trường

Trong một số IdP/cloud platform, **application registration** chứa thông tin khai báo của ứng dụng, còn **service principal** là thực thể đại diện ứng dụng trong một tenant/directory, nơi grants/consent có thể gắn vào.

Ví dụ tổ chức có một sản phẩm **reporting-platform**, triển khai:

~~~text
Business application: reporting-platform
  ├─ Development workload principal
  │    └─ reports.test.read on test data
  ├─ Staging workload principal
  │    └─ reports.stage.read in staging tenant
  └─ Production workload principal
       └─ reports.read in tenant-vn, no admin
~~~

Không nhất thiết mỗi workload phải có một app registration riêng trong mọi platform, nhưng **ràng buộc trust, grants, owner và credential theo môi trường** phải được tách theo risk. Việc dùng cùng client secret cho development và production làm tăng khả năng **lộ production identity từ môi trường ít được bảo vệ hơn**.

### Kiểm tra trước khi tạo principal

1. Application có **business purpose, catalog ID và owner** chưa?
2. Có thể tái sử dụng identity hợp lệ của platform hay cần principal mới?
3. Phải tách **tenant/environment/scope** thành các principal riêng không?
4. Ai được quyền đăng ký app, tạo credential, cấp consent và chỉnh trust policy?
5. Có policy **approval của API/resource owner** cho application permissions không?
6. Có khả năng kiểm **who can impersonate/assume** principal?
7. Có **decommission date, review cadence và incident owner** không?

**Tạo registration không tương đương đã cấp quyền vào tài nguyên**. Grants/consent, IAM role bindings, resource policies và runtime checks là những bước riêng.

## 12. Application identity và RBAC/ABAC

**RBAC** có thể gán app role như REPORTS_READER cho application principal. **ABAC** có thể giới hạn theo workload name, tenant, environment, namespace, resource classification, owner hoặc context.

### Mô hình quyền hẹp

~~~yaml
policyId: finance-app-read
principalType: APPLICATION
subject:
  applicationId: report-worker
  environment: production
  ownerTeam: finance-platform
  trustedRuntimeIdentity: true
action: invoice.summary.read
resource:
  tenant: tenant-vn
  classificationAtMost: INTERNAL
context:
  tokenAudience: finance-api
  networkOrWorkloadAttestationRequired: true
effect: PERMIT_WHEN_ALL_MATCH
default: DENY
~~~

Đây là **pseudoconfiguration**, không phải cú pháp của một policy engine cụ thể. Các thuộc tính subject phải được **ràng buộc bằng nguồn tin cậy**, không lấy nguyên văn từ HTTP body của ứng dụng. Backend nên đọc tenant/classification của resource từ hệ thống có thẩm quyền.

### Cần kiểm cả permission lẫn đường nâng quyền

Một application principal có thể chỉ có REPORTS_READER, nhưng:

- Có quyền **read toàn bộ secrets** của một service admin.
- Có quyền **assumeRole** vào một principal khác mạnh hơn.
- Có thể sửa **trust policy** của role đích.
- Có thể thay **CI/CD pipeline** chạy bằng quyền production.
- Có quyền **grantRole** hoặc quản trị account khác.

Vì vậy least privilege phải đánh giá **effective capabilities và privilege escalation paths**, không chỉ các scopes được in trong token.

## 13. Quản lý application identity theo vòng đời JML

Mô hình JML của nhân viên có thể chuyển thành vòng đời phù hợp cho ứng dụng:

| Giai đoạn của ứng dụng | Tương ứng JML | Mục tiêu kiểm soát |
| --- | --- | --- |
| **Design/Registration** | Trước Joiner | Xác định owner, purpose, trust và phạm vi quyền. |
| **Onboarding/Activation** | Joiner | Tạo principal, cấp trust và grants được duyệt, kiểm API. |
| **Scaling/Deployment** | Mover về ngữ cảnh | Thêm replica/region không tự mở rộng quyền. |
| **Change of owner/scope** | Mover | Reapprove quyền và trust, loại grants cũ, rotate credential nếu cần. |
| **Key/certificate rotation** | Chăm sóc vòng đời | Đổi credential không làm mất control của principal hoặc gián đoạn không cần. |
| **Risk/Access review** | Rà soát định kỳ/sự kiện | Đối soát actual vs desired và runtime usage. |
| **Suspension/Incident containment** | Tạm khóa | Chặn token/grants/traffic, cô lập workload và khôi phục có kiểm soát. |
| **Decommission/Offboarding** | Leaver | Revoke grants, trust, keys, service accounts và verify access DENY. |

### Đừng đồng nhất Leaver của nhân viên với Leaver của ứng dụng

Khi người phát triển hoặc owner nghỉ công ty, ứng dụng có thể vẫn phục vụ khách hàng. Không tự xóa service principal gây downtime. Phải **chuyển ownership, gỡ quyền người cũ trên repository/CI/CD/vault, đánh giá credential từng biết và đặt owner chịu trách nhiệm mới**.

Ngược lại, khi ứng dụng đã decommission, dù nhân viên owner còn ACTIVE, **application principal và credentials không được tồn tại vô hạn** chỉ vì account nhân sự vẫn dùng được.

## 14. Joiner: quy trình tạo một application identity an toàn

Một quy trình onboarding có thể theo các bước:

1. **Đăng ký nhu cầu**: application/service ID, chức năng, data flows, owner, tenant, môi trường.
2. **Xác minh provenance**: repository/project, deployment pipeline, runtime, nhà cung cấp phần mềm, sponsorship.
3. **Chọn mô hình xác thực**: managed identity/federation nếu nền tảng hỗ trợ, nếu không đánh giá certificate/private_key_jwt/secret.
4. **Tạo principal theo môi trường**: ID ổn định, owner và định danh target tương ứng.
5. **Ràng buộc trust chặt**: issuer, subject, audience, namespace/repo/environment, approved role.
6. **Định nghĩa least privilege**: actions, resource scopes, tenants, thời hạn, network/context.
7. **Kiểm SoD/privilege chains**: application có thể tự phê duyệt, grant quyền hoặc che audit không?
8. **Approval đúng authority**: owner ứng dụng, API/data owner và security/platform tùy rủi ro.
9. **Provision và quản lý credentials an toàn**: không đưa secret vào source control hoặc build log.
10. **Readback** principal, trust policy, grants, credential metadata và token audience.
11. **Positive/negative test**: API hợp lệ ALLOW; cross-tenant/admin/unapproved actions DENY.
12. **Đưa vào inventory**: purpose, owner, credentials, TTL, rotation, audit và expiry/decommission trigger.

### Không dùng tài khoản chung mặc định

Khi nhiều jobs dùng chung một principal, log khó biết **job nào** đã gây hành động, khó thu hồi một integration mà không ảnh hưởng các integration còn lại, và blast radius khi secret lộ sẽ lớn. Cân nhắc **mỗi workload theo nhiệm vụ/rủi ro một principal** hoặc một binding có attribution đủ chi tiết, thay vì một tài khoản admin dùng chung.

## 15. Mover: ứng dụng đổi quyền, môi trường hoặc chủ sở hữu

Application Mover xảy ra khi:

- Chức năng từ **read-only** sang **write/export**.
- Chuyển từ staging lên production.
- Thêm tenant/region hoặc tích hợp API mới.
- Thay owner/team quản lý, repository hoặc CI/CD runner.
- Chuyển từ static secret sang federation/managed identity.
- Thay AS/IdP issuer, certificate trust, token exchange hoặc role mappings.

### Phân loại thay đổi và hành động

| Thay đổi | Trước khi áp | Sau khi áp |
| --- | --- | --- |
| Thêm API permission | Risk/SoD/owner approval, resource scope. | Verify API ALLOW đúng scope và DENY ngoài scope. |
| Thay tenant | Kiểm trust/consent giữa tenants, dữ liệu phân vùng. | Revoke grants tenant cũ không còn dùng. |
| Chuyển environment | Tách identity, trust, CI/CD protections. | Test staging principal không vào production. |
| Thay owner | Kiểm quyền repository, vault, CI/CD, credential custody. | Remove former owner, reassign incident contact, rotate khi cần. |
| Thay issuer/credential | Đánh giá khả năng migration, dual-key overlap. | Revoke credential/trust cũ sau xác minh cutover. |
| Giảm quyền ứng dụng | Xác định đường role, ACL, scope, token đang tồn tại. | Readback và verified DENY với quyền bị gỡ. |

**Mỗi lần thay đổi quyền phải xét quyền cũ có thực sự mất hay không**. Chỉ thêm role mới rồi để role cũ tồn tại sẽ tích lũy quyền tồn dư theo thời gian.

## 16. Leaver/decommission: thu hồi application identity có kiểm chứng

Decommission là thời điểm dễ sót application principals vì application có thể đã tắt nhưng credentials/trust vẫn hợp lệ.

### Danh mục cần xử lý

1. **Disable hoặc xóa principal/app registration** theo policy/provider và phụ thuộc thực tế.
2. **Revoke application grants/app roles/cloud IAM bindings** ở API và target resources.
3. **Thu hồi client secrets, private keys, certificates** và các trust binding không còn dùng.
4. **Revoke refresh tokens/grants**, nếu luồng có sử dụng chúng; xử lý access tokens đã phát riêng.
5. **Remove workload federation mappings** (issuer/subject/audience/role trust).
6. **Dọn ServiceAccount/namespace bindings** và workload identities không còn chạy.
7. **Revoke hoặc rotate API keys/PATs** được tạo riêng ở SaaS/legacy target.
8. **Dọn direct ACL, scheduled jobs, delegated grants, local integration accounts** liên quan.
9. **Kiểm quyền impersonate/assumeRole** hoặc secret access của principals khác vào app đã nghỉ.
10. **Giữ audit/evidence và dữ liệu nghiệp vụ cần lưu** theo retention trước khi xóa metadata.

### Thứ tự an toàn

Ngừng traffic/job và xác nhận các dependency đã được chuyển sang principal hợp lệ trước khi xóa credential; trong incident nghiêm trọng, có thể phải **chặn ngay các đường nhạy cảm** theo quy trình ứng cứu. Không duy trì principal “phòng khi cần” vô hạn mà không owner, expiry hay approved exception.

### Revoke accepted khác verified

Một API trả HTTP 200/204 khi xóa role **không tự chứng minh mọi Resource Server đã chặn token đang lưu**. Cần kiểm:

- Token cũ còn hạn có được RS chấp nhận không và trong bao lâu.
- Có app-local ACL hoặc session độc lập không.
- Federation trust có còn cho nhận token mới không.
- Service principal khác có thể impersonate hoặc dùng credential cũ không.
- Tất cả targets bắt buộc đã được **readback/negative probe** đúng chưa.

Nếu một target không thể kiểm, ghi **UNVERIFIED/COVERAGE_GAP**, không gán PASS.

## 17. Quản lý credential và luân chuyển không gián đoạn

Credential là một **tài sản có vòng đời** gắn với application identity. Một principal có thể dùng nhiều credential trong giai đoạn chuyển đổi; mỗi credential cần được kiểm soát riêng.

### Credential inventory

| Thuộc tính | Mục đích |
| --- | --- |
| Credential ID / key ID | Phân biệt các khóa của cùng principal. |
| Credential type | Client secret, private key, certificate, token binding, workload federation. |
| IssuedAt, validFrom, expiresAt | Theo dõi thời hạn và giai đoạn overlap. |
| Owner/rotation operator | Người hoặc hệ thống chịu trách nhiệm. |
| Usage/lastSeen và nguồn telemetry | Phát hiện credential cũ, nhưng không nhầm thiếu log với không dùng. |
| Bound application/tenant/environment | Không dùng nhầm credential môi trường khác. |
| Storage/control | Vault/KMS/HSM, runtime injection, hạn chế export. |
| Revocation status và evidence | Phân biệt đã yêu cầu revoke với đã chặn tại verifier. |
| Incident/compromise reference | Xử lý ưu tiên khi credential nghi bị lộ. |

**Không lưu giá trị secret hoặc private key trong bảng inventory hay audit**, chỉ lưu metadata cần quản trị. Một credential cần được đặt trong vault/kho bảo mật phù hợp, có kiểm soát đọc và dấu vết.

### Quy trình rotation có kiểm soát

~~~mermaid
flowchart TD
    A["Credential sắp hết hạn / nghi bị lộ / policy trigger"] --> B["Chốt owner, affected consumers, scope, risk"]
    B --> C["Tạo credential mới hoặc federation binding mới"]
    C --> D["Cập nhật workload runtime/vault bằng kênh an toàn"]
    D --> E["Test token issuance + API ALLOW/DENY đúng scope"]
    E --> F{"Đã xác minh consumers chuyển sang mới?"}
    F -->|Chưa| G["Điều tra / rollback có kiểm soát"]
    G --> D
    F -->|Rồi| H["Thu hồi credential cũ / trust cũ"]
    H --> I["Verify credential cũ không còn được chấp nhận"]
    I --> J["Audit, đóng rotation, kiểm alerts"]
~~~

Trong trường hợp **credential bị lộ**, quy trình ứng cứu có thể yêu cầu thu hồi ngay thay vì duy trì overlap để tránh downtime. Với rotation bình thường, giai đoạn overlap cần ngắn, có deadline, telemetry và owner rõ.

### Những lỗi rotation thường gặp

- Xoay vòng secret ở IdP nhưng ứng dụng vẫn dùng bản cũ trong container image.
- Cấp credential mới mà không gỡ credential cũ; cửa sổ bị lạm dụng kéo dài.
- Xóa credential trước khi mọi replica chuyển đổi, gây gián đoạn dịch vụ.
- Update vault nhưng app không reload, tiếp tục lỗi authentication.
- Ký JWT với key mới nhưng resource server cache JWKS quá cũ.
- Cert mTLS hết hạn nhưng monitoring chỉ nhìn client secret.
- Thay issuer/subject federation nhưng giữ trust binding wildcard cũ.

### Không suy luận từ số lần sử dụng

Credential ít xuất hiện trong log có thể dùng cho **disaster recovery**, một job định kỳ hoặc do thiếu telemetry. Trước khi vô hiệu hóa cần xác nhận dependency/owner, nhưng credential không owner, rủi ro cao hoặc đã bị lộ phải được xử lý theo policy chứ không đợi đủ số ngày “unused”.

## 18. Least privilege và access certification cho application principal

Một review có chất lượng nên đối chiếu:

\[
\text{PotentialExcess} =
\text{EffectiveAppPermissions} \setminus \text{ApprovedBusinessNeed}
\]

Phép trừ tập ở trên chỉ là mô hình. Với scope wildcard, RBAC inheritance, conditions của ABAC và permissions động, cần chuẩn hóa action/resource/context hoặc kiểm bằng policy simulator/PEP; không thể chỉ so chuỗi tên role.

| Đối tượng review | Câu hỏi |
| --- | --- |
| Business purpose | Workload còn phục vụ nghiệp vụ không? Có owner chịu trách nhiệm? |
| Application principal | Principal này có đang dùng ở production/staging hoặc đã decommission? |
| OAuth client grants | Có scope/app roles rộng hơn những API calls thực sự cần? |
| Cloud IAM permissions | Có wildcard, trust cross-account/cross-project hoặc quyền quản trị không? |
| Service account bindings | Namespace, pod/runtime và người có thể impersonate có đúng? |
| Secrets/keys | Có credential dài hạn, quá hạn, không rotate hoặc bị biết bởi Leaver? |
| Conditional policies | Tenant, environment, classification, audience và time windows có được enforce? |
| Logs/evidence | Có chứng minh ALLOW/DENY tại target và nguồn workload identity không? |
| Expiry/decommission | Không còn workload vẫn còn role/trust/token không? |

### Quyết định review

- **KEEP:** app vẫn cần, scope tối thiểu, owner và evidence hợp lệ.
- **REDUCE/CHANGE:** giảm grants, chuyển secret sang federation, tách staging/production, thêm expiry.
- **REVOKE/DECOMMISSION:** app không còn dùng hoặc quyền không được phê duyệt.
- **INVESTIGATE:** thiếu owner, principal mapping hoặc trạng thái actual không rõ.
- **EXCEPTION:** chỉ khi policy cho phép, có owner, scope, TTL, controls và audit.

**Không tự động KEEP** khi owner không trả lời hoặc vì application identity không có human manager. Workload phải có **application/service owner thực** và tuyến escalation phù hợp.

## 19. Service ownership và trách nhiệm của con người

Application identity **không phải một con người**, nhưng vẫn phải có người/nhóm chịu trách nhiệm quản lý.

| Vai trò | Trách nhiệm |
| --- | --- |
| **Business owner** | Xác nhận ứng dụng còn phục vụ mục đích nào và dữ liệu cần truy cập. |
| **Technical/application owner** | Quản lý code, deployment, runtime, principal và dependencies. |
| **API/resource owner** | Duyệt actions/tenant/resource scope của target API. |
| **Identity/IAM operator** | Đăng ký principal, grants, policy, inventory và reconciliation. |
| **Security/platform reviewer** | Kiểm credential model, trust federation, privilege escalation và SoD. |
| **Credential custodian** | Bảo vệ và luân chuyển secrets/keys theo policy. |
| **Auditor/verifier** | Kiểm quyết định đã áp, truy vết risk/exception và verified revocation. |

### Khi owner là Leaver hoặc Mover

1. HRIS báo thay đổi nhân sự với stable subject ID và effectiveAt.
2. Inventory truy ngược các **application principals/workload secrets** mà người đó sở hữu hoặc có quyền điều khiển.
3. Chọn owner mới và xác minh acceptance trước khi bỏ mọi kênh incident support.
4. Thu hồi quyền người cũ trên **vault, repository, CI/CD, cloud role, app registration, trust policy**.
5. Đánh giá rotate credentials mà người cũ có thể từng đọc; ưu tiên theo độ nhạy và threat model.
6. Kiểm applications còn hoạt động và không mất quyền hợp lệ do thay owner.
7. Ghi audit, cập nhật owner reference và deadline review tiếp.

**Tách việc chuyển owner khỏi việc cấp thêm quyền cho owner mới**: người mới không mặc nhiên cần global admin; sử dụng roles tối thiểu và approval phù hợp.

## 20. SoD và những đường leo thang quyền qua application identity

**Separation of Duties (SoD)** không chỉ áp dụng cho con người tạo–duyệt giao dịch. Application identity có thể bị dùng để **hành động thay hoặc vượt quyền user**.

### Ví dụ xung đột

| Khả năng A | Khả năng B | Rủi ro |
| --- | --- | --- |
| CI bot có quyền sửa build workflow. | Cùng bot có quyền self-approve release production. | Bỏ qua code review/independent approval. |
| Service có quyền tạo payment. | Service cũng approve cùng payment. | Không còn kiểm soát maker–checker độc lập. |
| Principal sửa IAM policy. | Principal cũng xóa audit trail. | Tự che giấu privilege escalation. |
| User điều khiển app Creator. | Cùng user assume app Approver. | Hai service accounts nhưng không có independent actor. |
| Connector có quyền grantRole. | Connector tự quyết request nào được duyệt. | Tự cấp quyền ngoài approval. |

### Biện pháp

- Tách **authorizer/approver** khỏi **technical executor**.
- Xác minh **user/delegation origin** nếu một workload hành động thay người.
- Chặn **self-approval** ở backend nghiệp vụ, không chỉ bằng tên service principal.
- Kiểm **impersonation, service account token creation, secret-read và trust-policy modification**.
- Thực hiện **readback và no-side-effect tests** trên các API quan trọng.
- Ghi cả **technical actor** và **business initiator** khi phù hợp, không làm lẫn audit attribution.

**Hai service principals khác nhau không đảm bảo độc lập** nếu cùng một người hoặc pipeline có quyền điều khiển cả hai.

## 21. Multi-tenancy và consent: application access có phạm vi

Một ứng dụng có thể hoạt động ở nhiều tenants hoặc organization accounts. Khi được **consent/grant** trong một tenant, không suy ra mọi tenant khác đều tin hoặc cho cùng permissions.

### Những loại phạm vi

| Chiều | Ví dụ | Rủi ro |
| --- | --- | --- |
| Tenant/directory | tenant-vn, tenant-sg | Cross-tenant data leak nếu resourceId/tenant thiếu kiểm. |
| Environment | dev/staging/prod | Staging workload assume production identity. |
| Resource | 1 bucket/project/namespace | Wildcard biến thành quyền toàn account. |
| API audience | finance-api, crm-api | Token audience confusion giữa các APIs. |
| Permission | reports.read, report.export | Read-only bị hiểu thành quyền export. |
| Time | 30 phút JIT | Grant/credential còn hiệu lực sau expiry. |
| Data classification | PUBLIC/INTERNAL/RESTRICTED | Ứng dụng đọc dữ liệu vượt classification cho phép. |

### Quy tắc khi onboarding tích hợp đa tenant

1. Kiểm **service principal/tenant mapping** và issuer được tin cậy.
2. Yêu cầu **approval/consent của người có thẩm quyền** tại target tenant.
3. Chỉ cấp scopes/app roles **cần thiết trong từng tenant**.
4. Backend xác định tenant/resource từ dữ liệu đã xác minh, không chỉ path/header từ client.
5. Kiểm những endpoints có thể truy cập bằng **client credentials** mà không có user.
6. Khi offboard tenant, revoke **grants và tokens/trust liên quan** cho tenant đó, tránh ảnh hưởng các tenant khác.

**Tenant ID trong token không tự chứng minh quyền vào mọi tài nguyên mang tenant đó**; object-level authorization vẫn cần khi request đến RS.

## 22. Chặn confused deputy và identity substitution

**Confused deputy** xảy ra khi một dịch vụ có đặc quyền bị sử dụng để thực hiện hành động mà bên gọi không được phép, do không ràng buộc mục đích hoặc bối cảnh ủy quyền.

### Ví dụ

~~~text
User Alice chỉ được đọc hóa đơn tenant A.
Frontend gọi report-worker bằng invoiceId của tenant B.
report-worker có app-only quyền đọc mọi tenant.
Nếu report-worker tin invoiceId do client đưa và dùng app token
để tải dữ liệu tenant B => Alice vượt quyền qua application identity.
~~~

Để ngăn:

- Phân biệt **user request authorization** và **app-to-app authentication**.
- Kiểm user được phép truy cập **đúng resource** trước khi dùng app-only credential.
- Ràng buộc **tenant, action, resource IDs** vào policy, không để client tự tuyên bố.
- Dùng token **audience hẹp**, sender constraints hoặc delegated/OBO khi phù hợp.
- Nếu request cần danh tính user, ghi và truyền **delegation context đã xác thực** theo contract.
- API downstream kiểm resource policy thay vì chỉ kiểm ứng dụng có scope read.

**Application identity là đại diện của phần mềm, không phải giấy phép cho mọi người dùng mượn đặc quyền ứng dụng**.

## 23. Audit và các sự kiện cần ghi

Một hệ thống quản lý application identity cần ghi dấu vết ở **cả control plane và data plane**.

| Sự kiện | Bằng chứng nên lưu | Mục đích |
| --- | --- | --- |
| Application registered | app/principal IDs, owner, environment, purpose, approval ref. | Biết danh tính từ đâu. |
| Credential created/rotated/revoked | key reference, type, timestamps, operator, evidence. | Kiểm vòng đời credential. |
| Trust policy changed | issuer/subject/audience binding diff và approver. | Tìm mở rộng khả năng assume role. |
| App permission granted | target, tenant, scope/role, owner, validity, decision. | Traceability của quyền cấp. |
| Token issued/rejected | client/principal ref, grant type, aud, reason, timestamp. | Phát hiện lạm dụng identity/token. |
| API accessed/denied | app/subject, action, resource class, tenant, policy outcome. | Xác minh business authorization. |
| Owner changed | old/new owner refs, effectiveAt, handover approval. | Không để principal mồ côi. |
| Credential suspected compromised | incident, containment/revoke status. | Ưu tiên xử lý. |
| App decommissioned | grants/trust/credentials removed, verified targets. | Ngăn quyền tồn dư. |

### Không lưu secrets trong audit

Không ghi **access/refresh token, client secret, private key, API key, ServiceAccount bearer token, session cookie hoặc dữ liệu tài chính chi tiết**. Khi cần liên kết sự kiện, dùng **request ID, credential ID, hashed reference được bảo vệ hoặc correlation ID** theo chính sách, tránh tạo một kho credential trong SIEM.

### Phân biệt dấu vết identity và hành động nghiệp vụ

Một token được cấp cho app là sự kiện **authentication/authorization grant**, chưa chứng minh app đã thực hiện hành động. Một API request được phép là sự kiện **data-plane authorization**, chưa chứng minh business outcome đã commit. Với thao tác ghi, audit có thể cần ghi **transaction result và no-side-effect on DENY**.

## 24. Số liệu và tín hiệu sức khỏe của application identity

| KPI / tín hiệu | Định nghĩa | Cảnh báo khi diễn giải |
| --- | --- | --- |
| **Owned application identity coverage** | Tỷ lệ principal có owner/purpose/target hợp lệ. | Owner trên giấy nhưng đã Leaver phải coi là gap. |
| **Static secret share** | Tỷ lệ workload phụ thuộc credential tĩnh theo scope đã đo. | Không mặc định federation phù hợp mọi legacy app. |
| **Credential expiration/rotation compliance** | Credential đúng thời hạn và đã rotate/revoke theo policy. | Metadata update khác với verifier đã từ chối key cũ. |
| **Overprivileged service principals** | App grants/roles không có nhu cầu hợp lệ hoặc wildcard. | Cần effective access, không chỉ đếm role. |
| **Cross-environment trust violations** | Dev/staging có thể assume production identity trái policy. | Có thể phải test trust thực, không chỉ xem config. |
| **Dormant principal count** | Principal không ghi nhận usage trong cửa sổ đo. | Thiếu log hoặc DR job không tự thành “không dùng”. |
| **Unapproved consent/grant** | Quyền API mới thiếu owner/approval. | Consent có thể nhiều tenant và nhiều nguồn. |
| **Decommission residual count** | Principals/tokens/trust còn cho truy cập sau ngày kết thúc. | Không chỉ đếm apps đã xóa khỏi catalog. |
| **Verified revocation latency** | Thời gian từ effectiveAt đến DENY trên PEP/target bắt buộc. | Không thay bằng thời gian connector trả 204. |
| **Workload token anomaly** | Token audience/client/grant bất thường, issuance surge. | Cần xét behavior baseline, tránh false positives. |
| **Unverified critical paths** | Đường quyền high-risk không có readback hoặc PEP probe. | Unknown không bằng zero risk. |

### Đừng đo “ít danh tính” làm mục tiêu

Một service account chung cho 100 jobs có thể khiến inventory chỉ có một principal, nhưng rủi ro tập trung và audit attribution tệ hơn. Mục tiêu đúng là **định danh phù hợp ranh giới trách nhiệm và least privilege**, không đơn thuần giảm số lượng principal.

## 25. Handling sự cố lộ credential của application identity

Khi nghi ngờ secret, certificate private key hoặc workload token bị lộ, phải có playbook tương ứng:

1. **Xác nhận loại principal, credential và phạm vi**: app ID, tenant, audiences, scopes, environments.
2. **Giới hạn tác động tức thời** theo risk: revoke credential/grant hoặc chặn network/API/role theo incident policy.
3. **Không giả định rotation xóa token đã cấp**: kiểm khả năng của AS/RS và cửa sổ TTL/revocation.
4. **Tìm abuse signals**: anomalous token issuances, cross-region calls, new role grants, API exports.
5. **Bảo vệ bằng chứng**: audit references, timestamps, change history, không công khai secret vào ticket.
6. **Cấp lại bằng trust model tốt hơn**: giảm quyền, dùng short-lived/federated identity khi phù hợp.
7. **Xác minh app hợp lệ vẫn hoạt động** sau containment/cutover.
8. **Kiểm credential cũ không còn được chấp nhận** tại các verifier/PEP trong scope.
9. **Kiểm các trust/permission chains** có thể đã bị thay đổi để duy trì truy cập.
10. **Post-incident review**: owner, CI/CD, secret storage, logging, detection và rotation cadence.

**Phản ứng với credential bị lộ là quy trình an ninh có ưu tiên containment**, không phải rotation thường kỳ. Độ dài cửa sổ chuyển đổi phải được cân bằng với nguy cơ bị lạm dụng, không cam kết một kịch bản “zero downtime” bất chấp bằng chứng compromise.

## 26. Java pseudocode: ứng dụng nhận token bằng workload identity

Với một workload chạy trong môi trường hỗ trợ managed/federated identity, ứng dụng có thể nhờ **credential provider của platform** lấy token dành cho đúng API mà không tự chứa client secret.

Ví dụ sau là **pseudocode kiến trúc**, không phải API có thể chạy ngay của một cloud SDK:

~~~java
// Pseudocode: không tự viết giao thức exchange token bằng tay trong production.
record WorkloadToken(String value, String audience, java.time.Instant expiresAt) {}

interface TrustedWorkloadCredentialProvider {
    WorkloadToken acquireTokenFor(String resourceAudience, String approvedScope);
}

final class FinanceReportClient {
    private final TrustedWorkloadCredentialProvider credentialProvider;
    private final FinanceApiTransport transport;

    FinanceReportClient(
            TrustedWorkloadCredentialProvider credentialProvider,
            FinanceApiTransport transport) {
        this.credentialProvider = credentialProvider;
        this.transport = transport;
    }

    ReportSummary loadApprovedTenantSummary(String tenantId) {
        WorkloadToken token = credentialProvider.acquireTokenFor(
            "finance-api",
            "reports.read"
        );

        if (token == null
                || !"finance-api".equals(token.audience())
                || !token.expiresAt().isAfter(java.time.Instant.now())) {
            throw new SecurityException("Unable to obtain valid workload token");
        }

        // Transport phải dùng TLS, không log bearer token.
        // TenantId không được xem là authorization chỉ vì client gửi lên.
        return transport.getApprovedSummary(token.value(), tenantId);
    }
}
~~~

### Những điểm cần hiện thực bằng thư viện/nền tảng đáng tin

1. **Token acquisition**: dùng SDK chính thức hoặc component được tổ chức phê duyệt; không tự bỏ kiểm signature/issuer/audience.
2. **Credential availability**: workload chỉ có quyền lấy token khi runtime/subject binding đã được chứng minh.
3. **Token cache**: cache ngắn hạn theo audience/scope, có xử lý expiry và chủ động làm mới theo SDK contract.
4. **Transport security**: TLS, endpoint allowlist và hạn chế redirect làm lộ bearer token.
5. **Exception handling**: không fallback sang một static admin credential nếu token federation không lấy được.
6. **Audit**: ghi principal ID, operation, target và kết quả, không ghi token value.
7. **Least privilege**: application principal chỉ có quyền reports.read và resource scope tương ứng.

**Phần kiểm token.audience ở client chỉ là kiểm tra phòng vệ cục bộ**, không thay thế kiểm chứng của API. Một client không thể tự tuyên bố token hợp lệ; **Resource Server mới là nơi xác thực và quyết định quyền**.

## 27. Java pseudocode: Resource Server kiểm application identity

Thực tế nên dùng **OAuth2 Resource Server/JWT validation middleware** có cấu hình issuer, signing keys, accepted algorithms, audience và thời hạn. Không tự viết phương thức parse JWT rồi tin claims không được xác minh.

Ví dụ sau giả định tầng framework **đã xác minh access token** trước khi tạo đối tượng VerifiedToken:

~~~java
import java.util.Set;

record VerifiedToken(
    String issuer,
    String audience,
    String principalId,
    String clientId,
    Set<String> scopes,
    boolean isApplicationOnly,
    boolean isFromTrustedIssuer
) {}

record InvoiceSummaryResource(
    String tenantId,
    String classification
) {}

final class FinanceApplicationAuthorization {
    boolean mayReadSummary(VerifiedToken token, InvoiceSummaryResource resource) {
        if (token == null || resource == null) {
            return false;
        }

        // VerifiedToken phải được tạo từ verifier của framework,
        // tuyệt đối không lấy từ các header do client tự khai.
        return token.isFromTrustedIssuer()
            && "finance-api".equals(token.audience())
            && token.isApplicationOnly()
            && "report-worker-prod".equals(token.clientId())
            && token.scopes() != null
            && token.scopes().contains("reports.read")
            && "tenant-vn".equals(resource.tenantId())
            && "INTERNAL".equals(resource.classification());
    }
}
~~~

### Mục đích của mẫu

- **Client được xác định** từ issuer contract, không từ header X-Client-Id.
- **Audience đúng** cho Finance API; token của CRM không đủ dùng.
- **Principal type đúng**: quyền app-only, không nhầm delegated user token.
- **Action scope rõ**: reports.read không đồng nghĩa report.export hoặc invoice.approve.
- **Resource scope** lấy từ dữ liệu backend; không tin tenantId do client tự khai.
- **Default deny** khi token/resource thiếu điều kiện.

**Giới hạn:** đoạn code chỉ minh họa cách kết hợp các kiểm tra, không bao quát mọi trường hợp. Trong thực tế claims có thể dùng roles thay scope cho app-only, issuer có thể khác tên trường client ID và classification có thể có nhiều cấp. Mapping phải theo provider contract, có kiểm thử và không dùng kết quả một trường duy nhất để quyết định.

### Không bỏ sót OAuth token verification

Tầng xác thực token cần kiểm **signature/introspection, issuer, audience, expiration/not-before, thuật toán, key rotation, token type** và các ràng buộc client/sender nếu policy yêu cầu. Một chuỗi JSON bất kỳ chứa scope=reports.read **không trở thành access token hợp lệ**.

### Kiểm soát cấp quyền theo thời gian

Với quyền có TTL ngắn hoặc Leaver/decommission khẩn, API có thể cần **current-state/entitlement version check hoặc revocation mechanism** bên cạnh token tự chứa; nếu không, cửa sổ token cũ còn hiệu lực phải được đo và chấp nhận theo SLA.

## 28. Mẫu hồ sơ application identity và lifecycle events

Một catalog entry có thể mô tả:

~~~yaml
applicationIdentityId: appid-report-worker-prod
applicationName: report-worker
principalType: WORKLOAD
environment: production
tenantId: tenant-vn
owner:
  businessTeam: finance-reporting
  technicalTeam: platform-finance
  incidentContactRef: team-finance-oncall
purpose: Tong hop bao cao noi bo theo lich
runtime:
  kind: kubernetes
  namespace: finance-prod
  serviceAccount: report-worker
authentication:
  method: WORKLOAD_IDENTITY_FEDERATION
  trustedIssuerRef: cluster-issuer-prod
  allowedSubjectRef: system:serviceaccount:finance-prod:report-worker
  tokenExchangeAudience: finance-token-exchange
authorization:
  resourceServer: finance-api
  approvedActions: [reports.read]
  resourceScope: tenant-vn
  approvalRef: app-access-042
  policyVersion: finance-app-v5
credentialLifecycle:
  staticSecretPresent: false
  tokenMaxLifetimeByPolicySeconds: 900
governance:
  nextReviewDue: "2027-02-23"
  decommissionTrigger: project-closure
  status: ACTIVE
~~~

**Chỉ là YAML minh họa**, không phải schema chuẩn của cloud provider/SCIM. Một số policy có thể không hỗ trợ giới hạn token 900 giây; giá trị này là **mong muốn quản trị**, không được coi đã thực thi nếu thiếu xác nhận từ AS/RS. Chỉ số max lifetime cần đối chiếu khả năng của issuer và token actually issued.

### Lifecycle events tối thiểu

| Event | Dữ liệu quan trọng | Hành động |
| --- | --- | --- |
| APP_REGISTERED | appId, owner, scope, approved purpose. | Tạo inventory, chưa mặc định cấp quyền. |
| PRINCIPAL_ACTIVATED | principalId, runtime trust, grants, effectiveAt. | Verify authentication và authorization. |
| APP_PERMISSION_CHANGED | policy version, approved delta, old/new scope. | Reassess risk, apply, readback và test. |
| CREDENTIAL_ROTATED | credential ref, old/new state, verification. | Xác nhận consumers đã cutover, revoke credential cũ. |
| OWNER_CHANGED | old/new owner, HR change event, effectiveAt. | Thu hồi quyền owner cũ, kiểm secret custody. |
| APP_SUSPENDED | incident/suspension reason, scope. | Chặn active access theo incident policy. |
| APP_DECOMMISSION_REQUESTED | desired removal set, dependencies, effectiveAt. | Ngừng workload, revoke trust/grants/credentials. |
| APP_ACCESS_VERIFIED_REVOKED | target PEP refs, verifiedAt, evidence. | Đóng khi các đường bắt buộc đã DENY. |

### Chống sự kiện cũ ghi đè trạng thái mới

Giống JML của nhân viên, event provisioning workload cần **stable app/principal ID, revision/version, effectiveAt, idempotency key và current-state check**. Nếu job cũ gửi APP_ACTIVATED sau decommission, hệ thống không được tạo lại principal/quyền ngoài policy.

## 29. Ma trận kiểm thử application identity

Bộ test cần dùng **môi trường và principal được phép thử**, ưu tiên dữ liệu giả. Không sao chép private keys/secrets từ production vào fixture; khi cần kiểm key lifecycle sử dụng key thử riêng.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| AI01 | Workload có principal đúng, audience và scope reports.read. | ALLOW hành động hợp lệ đúng tenant. |
| AI02 | Client ID công khai nhưng không có credential/trust hợp lệ. | Không nhận được access token. |
| AI03 | Token có chữ ký giả hoặc issuer không tin cậy. | Resource Server từ chối. |
| AI04 | Token dành cho CRM API gửi vào Finance API. | DENY do sai audience. |
| AI05 | Access token hết hạn hoặc nbf tương lai. | DENY theo token validation. |
| AI06 | Workload có reports.read thử report.export. | DENY; scope không tự mở rộng. |
| AI07 | Workload tenant VN đọc resource tenant SG. | DENY resource tenant isolation. |
| AI08 | Client tự gửi X-Client-Id của principal khác. | Không thay identity đã xác minh. |
| AI09 | Client tự gửi resource.classification=PUBLIC. | Không ghi đè classification backend. |
| AI10 | Client không có user nhưng cố dùng delegated-only endpoint. | DENY hoặc chuyển đúng flow theo policy. |
| AI11 | Web app dùng app-only token để đọc object user không được phép. | Backend chặn confused deputy/cross-user access. |
| AI12 | OIDC ID token dùng thay access token tại API. | DENY, không chấp nhận sai token purpose. |
| AI13 | App-only token thiếu claim/role cần theo issuer contract. | DENY/fail-safe, không default ALLOW. |
| AI14 | Managed identity token endpoint bị gọi từ workload không được phép. | Không cấp token cho identity target. |
| AI15 | Federation assertion có issuer khác trust policy. | STS/AS từ chối exchange. |
| AI16 | Federation assertion có subject staging, xin role production. | DENY subject/environment mismatch. |
| AI17 | Federation assertion có audience khác STS yêu cầu. | DENY audience mismatch. |
| AI18 | Trust policy dùng wildcard repo rộng bất thường. | Risk review phát hiện và yêu cầu thu hẹp. |
| AI19 | K8s pod dùng ServiceAccount khác binding được duyệt. | Không được nhận production credential. |
| AI20 | K8s ServiceAccount không có Kubernetes RBAC nhưng có token. | Token không tự cấp quyền cluster/API bên ngoài. |
| AI21 | Credential mới hoạt động nhưng credential cũ chưa revoke. | Không đóng rotation; đánh dấu residual exposure. |
| AI22 | Credential cũ đã revoke nhưng JWT access token cũ còn hạn. | Đo RS behavior và xử lý theo revocation SLA. |
| AI23 | Client secret xuất hiện trong CI log. | Secret exposure incident/rotation workflow. |
| AI24 | Private key quá hạn hoặc certificate mTLS sai identity. | Authentication thất bại và có alert. |
| AI25 | Resource Server không cập nhật trust keys sau rotation. | Detect, xử lý key propagation, không tắt validation. |
| AI26 | Một principal dùng chung cho dev và production ngoài policy. | Detect và tách trust/grants phù hợp. |
| AI27 | App registration có nhưng chưa được resource owner consent. | Không tự có API permissions. |
| AI28 | Một tenant đã offboard, tenant khác vẫn dùng app. | Revoke đúng tenant, tránh xóa nhầm access hợp lệ. |
| AI29 | Role tên Reader được thay thành có quyền Export. | Detect catalog drift, reassess access. |
| AI30 | App owner là Leaver nhưng workload vẫn hợp lệ. | Chuyển owner, thu hồi quyền người cũ, không xóa bừa service. |
| AI31 | App decommission nhưng service principal vẫn có grant. | Residual access finding và revoke. |
| AI32 | Service principal bị delete nhưng PAT ở SaaS còn active. | Không VERIFIED; xử lý đường quyền cục bộ. |
| AI33 | Old workload federation subject vẫn được trust sau migration. | Revoke stale trust và thử exchange cũ DENY. |
| AI34 | Credential secret cũ bị retry sau rotation. | Client auth DENY, audit không lộ secret. |
| AI35 | Workload dùng quyền assumeRole để vượt granted scope. | Kiểm impersonation path, DENY nếu trái policy. |
| AI36 | Bot tạo và duyệt transaction mà policy yêu cầu độc lập. | Detect và DENY conflict SoD ở PEP. |
| AI37 | Policy trả DENY nhưng batch export vẫn tạo file. | FAIL no-side-effect; sửa missing PEP. |
| AI38 | API trả 503 do outage cho negative test. | Không được coi là verified DENY. |
| AI39 | App principal được tái tạo bởi event cũ sau decommission. | Idempotency/revision ngăn regrant. |
| AI40 | Target không có API readback grants. | Ghi UNVERIFIED/coverage gap và owner/remediation. |

### Cách chạy kiểm thử hiệu quả

1. Chọn **positive controls** chứng minh workload và API hợp lệ vẫn hoạt động.
2. Kiểm **trust boundary** trước: issuer, subject, audience, env, tenant.
3. Kiểm **token validation** tại resource server bằng test issuer/keys riêng.
4. Kiểm **least privilege**: action/resource/tenant không được duyệt phải DENY.
5. Kiểm **credential lifecycle**: issuance, rotation, old-key revoke và token expiry.
6. Kiểm **JML/decommission**: old trust và grants không sống lại.
7. Kiểm **fault paths**: STS/AS outage, PDP timeout, cache stale, connector partial failure.
8. Ghi evidence, owner, policy version và status VERIFIED/UNVERIFIED.

**Lỗi 401/403/404** có thể được sử dụng theo contract API để chặn lộ thông tin; cần xem **quyết định bảo mật, response body và no unauthorized effects**, không ép một mã HTTP duy nhất cho mọi hệ thống.

## 30. Tình huống thực hành: report-worker đi từ Joiner tới Leaver

### Bối cảnh và yêu cầu

Đội Finance có một job chạy hàng đêm để tổng hợp báo cáo nội bộ. Tài nguyên đích là **Finance API** có hai tenants VN và SG. Job chỉ được phép đọc **summary tài chính tenant VN**, không được approve payment, xem hóa đơn nhạy cảm của người khác hoặc truy cập admin API.

Tổ chức có một IdP/Authorization Server, Kubernetes cluster production, workload federation, IGA để duyệt grants, cloud IAM, vault và audit ở Finance API.

### Bước 1 – Onboard và xác định owner

Hồ sơ có:

~~~text
Business app ID       = report-worker
Workload principal    = report-worker-prod
Owner team            = finance-reporting
Runtime               = namespace finance-prod / ServiceAccount report-worker
Target resource       = finance-api
Approved action       = reports.read
Approved resource     = tenant-vn, classification INTERNAL
Credential strategy   = workload federation, no app-owned static secret
Security review       = permission scope + trust binding + audit
~~~

Đội ứng dụng và API owner đồng ý phạm vi trên, IAM tạo principal/binding, cấu hình issuer–subject–audience đúng deployment, chưa cấp quyền production cho principal staging.

### Bước 2 – Kiểm chứng khi activation

| Probe | Kỳ vọng | Vì sao |
| --- | --- | --- |
| Production report-worker xin token cho Finance API. | TOKEN ISSUED nếu trust hợp lệ. | Workload được xác thực đúng issuer/subject/audience. |
| Workload gọi reports.read tenant VN. | ALLOW. | Nhiệm vụ được phê duyệt. |
| Cùng workload gọi reports.read tenant SG. | DENY. | Tenant isolation. |
| Workload gọi invoice.export. | DENY. | Không có quyền export. |
| Workload gọi payment.approve. | DENY. | Không có app role/SoD entitlement. |
| Staging job thử assume production role. | DENY. | Trust binding tách môi trường. |
| Token của CRM API gửi vào Finance API. | DENY. | Audience/RS verification. |

**Chỉ khi cả positive và negative tests đạt** mới xác nhận ứng dụng được cấp đúng quyền. Token issuance success không thay thế API authorization.

### Bước 3 – Mover: job thêm chức năng export

Sau ba tháng, nhóm đề xuất **report.export** để gửi bảng thống kê sang hệ thống BI.

Đánh giá:

1. Có cần export dữ liệu gốc hay chỉ tổng hợp đã ẩn định danh?
2. Scope export thuộc tenant nào, classification nào, có chứa dữ liệu nhạy cảm không?
3. Có thể dùng endpoint chỉ trả dữ liệu tổng hợp thay quyền export diện rộng không?
4. Có approval của Finance data owner và BI owner không?
5. Role/scope thay đổi có mở đường sang dữ liệu SG hoặc admin không?
6. Có cần một principal riêng cho chức năng export để dễ revoke không?

**Không tự cộng quyền export vào role report-worker-prod đang có** nếu phạm vi/rủi ro khác. Nếu quyền được duyệt, cần cập nhật policy version và chạy lại ma trận negative tests.

### Bước 4 – Mover: chủ sở hữu nghỉ việc

Một nhân viên trong team Finance rời công ty; workload vẫn hợp lệ. IAM:

- Tìm những roles cá nhân có thể sửa app registration, trust, grants, vault/CI/CD.
- Thu hồi quyền người cũ và chuyển owner reference phù hợp.
- Đánh giá có cần rotate credential hoặc đổi CI/CD protection.
- Không xóa principal đang vận hành chỉ vì một người Leaver.
- Ghi owner mới, audit và review date.

### Bước 5 – Leaver: project đóng và app decommission

Khi Finance không còn cần report-worker:

1. Dừng scheduled job, kiểm dependency/data retention.
2. Thu hồi Finance API app grants, service account/binding và workload trust.
3. Disable/xóa principal/registration theo platform policy.
4. Xác minh staging/principal khác vẫn hoạt động nếu được dùng cho dịch vụ khác.
5. Kiểm assertion cũ không thể exchange thành token mới sau revoke.
6. Kiểm access token còn hạn có bị RS chặn trong SLA chấp thuận không.
7. Gỡ local PAT/secrets hoặc jobs nếu chúng từng được tạo ở target.
8. Lưu evidence và trạng thái hoàn tất **VERIFIED** chỉ sau kiểm tra các target bắt buộc.

### Trường hợp phát hiện quyền tồn dư

Giả sử principal đã bị xóa khỏi IdP nhưng một **SaaS PAT** từng cấp cho report-worker vẫn gọi được Finance legacy export endpoint. Campaign không được kết luận “decommission complete”; đây là **residual application access** cần revoke PAT, điều tra usage và bổ sung target vào inventory.

**Bài học:** application identity phải có **trách nhiệm quản trị xuyên suốt lifecycle**, chứ không phải một client ID được tạo rồi bị quên khi phần mềm ngừng chạy.

## 31. Những sai lầm thường gặp với application identity

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng account/mật khẩu nhân viên cho cron job. | Leaver làm hỏng dịch vụ hoặc secret bị chia sẻ không rõ owner. | Principal ứng dụng riêng và workload credential thích hợp. |
| Tưởng client_id là bí mật. | Cho phép giả danh client bằng ID công khai. | Dùng client authentication hoặc trust/attestation thực sự. |
| Tưởng app registration đồng nghĩa đã cấp quyền. | Nhầm trust/consent/permissions, khó kiểm actual. | Tách registration, principal, grants và resource policy. |
| Dùng OIDC ID token để gọi API. | Sai token purpose/audience, tạo token confusion. | Dùng access token dành cho RS và kiểm audience. |
| Tin JWT chỉ vì parse được JSON. | Nhận claims giả mạo, bypass authentication. | JWT verifier/introspection chính thức và validation đầy đủ. |
| Không kiểm token audience. | Token của API khác được dùng để truy cập sai resource. | Audience restriction tại RS/AS. |
| Không giới hạn tenant/resource khi app-only access. | Confused deputy và cross-tenant access. | API kiểm business authorization trên resource. |
| Cấp global admin cho mọi integration. | Blast radius rất lớn khi credential lộ. | Scope/app roles tối thiểu, trust chặt và owner approval. |
| Dùng chung một credential cho dev và prod. | Môi trường rủi ro thấp chiếm production. | Phân tách principal/credential/trust theo environment. |
| Federation trust dùng wildcard quá rộng. | Bất kỳ workload/repo/namespace nào cũng assume được role. | Ràng buộc issuer, subject, aud và production environment. |
| Tưởng Kubernetes ServiceAccount tự có cloud permissions. | Cấu hình trust sai hoặc grant không kiểm soát. | Tách K8s RBAC, workload assertion, cloud role binding và API authz. |
| Coi managed identity không có rủi ro credential. | Bỏ qua runtime compromise và token theft. | Giới hạn runtime, trust, TTL, scopes và monitoring. |
| Lưu private key trong repo/container image. | Credential bị sao chép, khó thu hồi. | Vault/HSM/KMS/secret manager, giới hạn export và rotation. |
| Xoay secret mới nhưng không revoke secret cũ. | Rủi ro tồn dư không giảm. | Overlap có giới hạn, verified old-key DENY. |
| Thu hồi secret rồi giả định mọi access token đã chết. | JWT cũ tiếp tục có hiệu lực ở RS. | TTL/revocation/current-state check theo kiến trúc. |
| Owner nhân viên nghỉ thì xóa ngay principal. | Gây downtime cho ứng dụng hợp lệ. | Chuyển owner, thu hồi quyền cũ, đánh giá rotation. |
| Project đóng nhưng giữ service principal vô hạn. | Ghost application identity với grants tồn dư. | Decommission workflow và verified revoke. |
| Bỏ qua local API key/PAT ở SaaS. | Đã xóa IdP principal nhưng API vẫn chấp nhận token local. | Inventory nhiều nguồn và readback tại target. |
| App-only token được dùng thay quyền của mọi user. | Người dùng có quyền hẹp gọi chức năng app rộng. | User authorization trước khi app thực hiện lời gọi thay. |
| Hai service accounts khác nhau coi là SoD đầy đủ. | Một controller vẫn có thể thực hiện cả hai bước. | Kiểm effective controller, impersonation, pipeline và approvals. |
| Chỉ đếm principal, không đánh giá quyền. | Một principal toàn quyền trông như posture tốt. | Capability/tenant/risk/privilege-hours và audit. |
| Chỉ kiểm API chính, bỏ batch/export workers. | Quyền vẫn được dùng qua đường không có PEP. | Test mọi enforcement paths quan trọng. |
| HTTP 503 được tính là DENY đúng policy. | Outage bị nhầm security success. | Positive controls và evidence quyết định. |
| Không kiểm event đến trễ/replay khi decommission. | App identity bị cấp lại sau khi xóa. | Revision, idempotency và current lifecycle state. |

## 32. Checklist triển khai application identity an toàn

1. **Mục đích xác định:** mỗi workload/app identity có application ID, business purpose và system catalog reference.
2. **Owner rõ:** business/technical owner, incident contact, escalation, không có principal không owner.
3. **Principal thích hợp:** không dùng human account hoặc shared admin tùy tiện cho automation.
4. **Ranh giới môi trường:** dev/staging/prod và tenants được phân tách phù hợp rủi ro.
5. **Trust binding chặt:** issuer, subject, audience, runtime/repository/namespace và TTL được xác minh.
6. **Mô hình credential:** ưu tiên credential ngắn hạn/managed/federated khi có khả năng; secret còn dùng được quản lý an toàn.
7. **Credential inventory:** key IDs, expiry, rotation, owner, storage, compromised indicators và revoke evidence.
8. **Least privilege:** API scopes/app roles đúng action/resource/tenant; không cấp wildcard theo thói quen.
9. **Resource-level authorization:** RS kiểm token và business policy, không coi OAuth token issuance là đủ.
10. **Delegation chính xác:** phân biệt app-only với user-delegated; ngăn confused deputy/on-behalf-of misuse.
11. **IdP/SSO/OIDC/OAuth mapping:** client/principal/issuer/aud/scope/roles được hiểu theo trust contract.
12. **SCIM và app-local grants:** không dùng SCIM success thay cho readback ở SaaS/legacy.
13. **Kubernetes/cloud identity:** tách K8s RBAC, cloud role grants, trust, API permissions.
14. **SoD:** người/công cụ không có thể tự tạo–tự duyệt hoặc che audit qua service identities.
15. **Joiner:** onboarding cần approval, principal creation, trust, grants và kiểm positive/negative.
16. **Mover:** đổi owner, quyền, issuer, environment, CI/CD hoặc credential phải reassess và revoke cũ.
17. **Leaver/decommission:** gỡ app grants, trust, keys, sessions/PATs, principal và xác minh target.
18. **Human owner Leaver:** không xóa workload hợp lệ một cách máy móc; chuyển owner và thu hồi quyền người cũ.
19. **Runtime provenance:** xác minh workload đang chạy trong deployment/trust domain đúng, không chỉ dựa client ID.
20. **Token validation:** issuer, signature/keys, alg, expiration, audience, type và app grant theo contract.
21. **Rotation:** overlap có giới hạn, kiểm consumer cutover và old credential bị từ chối.
22. **Incident response:** có playbook compromise secret, containment, token/grant review và recovery.
23. **Audit:** identity/credential/grant/usage/decommission events, không log secrets.
24. **PEP coverage:** API, admin, batch, background jobs, export và downstream paths được kiểm đúng.
25. **Verification:** tách REQUESTED, APPLIED, VERIFIED; không đóng trên HTTP success nếu chưa kiểm effective access.
26. **Coverage gaps:** quyền/tokens/legacy target chưa quan sát được phải có owner, severity và remediation.
27. **Change control:** role catalog, trust policy, app registration và grants có version/approval/audit.
28. **Continuous review:** rà soát theo rủi ro, sự kiện nhân sự, workload decommission và các quyền lâu không dùng.

**Tiêu chí kết thúc:** Application identity phải **được xác thực bởi nguồn đáng tin, chỉ được làm việc cần thiết, có owner và vòng đời kiểm soát được**. Đối với ứng dụng đã decommission, việc chấm dứt chỉ được coi VERIFIED khi các đường quyền trọng yếu đã bị từ chối theo phạm vi và SLA đã duyệt.

## 33. Câu hỏi tự kiểm tra

**Câu 1.** Application identity khác user identity ở đâu?

**Trả lời:** Application identity đại diện ứng dụng/workload khi xác thực và được cấp quyền; user identity đại diện người dùng. Một lời gọi có thể mang cả app context và delegated user context, nhưng hai nguồn quyền không thay thế nhau.

**Câu 2.** Client ID có phải mật khẩu bảo vệ OAuth client không?

**Trả lời:** Không. Client ID thường công khai, chỉ định danh client. Confidential client cần một cơ chế xác thực/trust phù hợp như mTLS, private_key_jwt, client secret hoặc workload federation theo AS contract.

**Câu 3.** Vì sao app registration chưa đủ để kết luận ứng dụng có quyền gọi Finance API?

**Trả lời:** Registration là metadata/configuration. Cần grants/consent, principal, token audience/scope và resource-level authorization mới xác định được API thực sự cho phép gì.

**Câu 4.** Client Credentials dùng trong trường hợp nào, và có đại diện cho user đã đăng nhập không?

**Trả lời:** Thường dùng cho confidential client máy–máy không cần user hiện diện. Nó cấp quyền ứng dụng theo grant/policy, không mặc nhiên đại diện cho quyền user.

**Câu 5.** Có thể dùng ID token của OIDC để gọi Resource Server không?

**Trả lời:** Không nên. ID token phục vụ client xác minh authentication result; protected API cần token đúng loại/mục đích, audience và policy, thường là access token.

**Câu 6.** Điều gì phải khớp khi cấu hình workload identity federation?

**Trả lời:** Issuer tin cậy, subject ràng buộc đúng workload, audience phù hợp STS/AS, expiry, môi trường/repository/namespace, trust policy và role permissions tối thiểu.

**Câu 7.** Kubernetes ServiceAccount có tự cho phép pod truy cập cloud storage không?

**Trả lời:** Không. Kubernetes ServiceAccount định danh workload trong cluster và có thể dùng cho Kubernetes RBAC; cloud access yêu cầu trust/federation và cloud IAM permissions riêng.

**Câu 8.** Vì sao không nên dùng chung một service principal cho staging và production?

**Trả lời:** Staging có thể có mức tin cậy thấp hơn; credential/trust chung có thể mở production khi staging bị chiếm. Tách principal/trust/grants theo ranh giới rủi ro làm giảm blast radius.

**Câu 9.** Một ứng dụng có reports.read scope có tự đọc mọi tài nguyên reports không?

**Trả lời:** Không. Resource Server cần kiểm tenant, classification, owner/resource scope và các policy business khác. Scope là một điều kiện, không thay thế authorization cho object cụ thể.

**Câu 10.** Vì sao rotation secret không chứng minh access token cũ đã mất hiệu lực?

**Trả lời:** Access token có thể được phát trước rotation và còn thời hạn ở RS. Cần TTL/revocation/introspection/current-state checks theo kiến trúc và kiểm effective access tại PEP.

**Câu 11.** Nếu owner của application identity nghỉ việc, có phải xóa principal ngay?

**Trả lời:** Không nhất thiết. Ứng dụng có thể vẫn đang phục vụ nghiệp vụ hợp lệ. Phải chuyển owner, thu hồi quyền cá nhân của người cũ, đánh giá credential rotation, rồi review grants.

**Câu 12.** Vì sao hai service accounts khác nhau không luôn bảo đảm SoD?

**Trả lời:** Nếu một người/workload có thể assume cả hai hoặc thay CI/CD pipeline của cả hai, quyền kiểm soát vẫn tập trung. Cần đánh giá effective controller và phê duyệt độc lập.

**Câu 13.** Khi decommission app registration, vì sao phải tìm cả PAT/local API keys?

**Trả lời:** Những credentials đó có thể do SaaS/legacy target quản lý riêng, không bị thu hồi khi xóa principal trong IdP. Phải kiểm mọi đường truy cập thực tế.

**Câu 14.** API trả 503 khi thử access token cũ sau decommission. Có thể báo quyền đã thu hồi không?

**Trả lời:** Chưa. Đây là lỗi khả dụng, không chứng minh authorization đã từ chối. Cần positive control và negative probe xác nhận resource server còn hoạt động và quyền thật sự DENY.

**Câu 15.** Dấu hiệu nào cho thấy một application identity đã được quản trị tốt?

**Trả lời:** Có owner/purpose rõ, trust/credential xác thực được, permission tối thiểu, phân tách môi trường, audit đủ, rotation/revocation có kiểm chứng, ứng dụng hợp lệ ALLOW và action ngoài scope DENY.

---

**Ghi nhớ:** **Application identity là danh tính của phần mềm, không phải tài khoản nhân viên dùng thay hoặc chỉ một client ID.** Một hệ thống an toàn phải quản lý **principal, credential, trust, OAuth token, RBAC/ABAC grants, người sở hữu và bằng chứng truy cập** như các đối tượng có vòng đời riêng. Với **Joiner–Mover–Leaver của ứng dụng**, cần **đăng ký đúng → cấp quyền hẹp → rà soát/luân chuyển khi thay đổi → thu hồi có xác minh khi decommission**, đồng thời xử lý ảnh hưởng từ **JML của người sở hữu**. Mục tiêu cuối là workload hợp lệ vẫn làm được nhiệm vụ, còn **quyền không còn cần thiết hoặc nằm ngoài phạm vi thực sự bị chặn tại Resource Server/PEP**, giảm **quyền truy cập tồn dư**.

# Phân biệt ủy quyền CAS Proxy với OAuth2 và lựa chọn phương án chuyển đổi

**CAS Proxy** và **OAuth 2.0** đều có thể xuất hiện trong bài toán “ứng dụng A gọi API B thay mặt người dùng”, nhưng chúng **không cùng một mô hình ủy quyền**. CAS Proxy chủ yếu **ủy nhiệm ngữ cảnh xác thực đã có** qua Proxy-Granting Ticket (**PGT**) và Proxy Ticket (**PT**) được cấp cho một service cụ thể. OAuth 2.0 là **khung cấp quyền truy cập tài nguyên**: Authorization Server (**AS**) cấp Access Token cho Client dùng với Resource Server (**RS**), có thể mang **scope**, **audience/resource**, thời hạn, danh tính client và bằng chứng ủy quyền.

**Không được đổi tên một PT thành OAuth Bearer token, dùng CAS username làm quyền API, hoặc cho API chấp nhận cả hai loại credential bằng một validator “dễ dãi”.** Khi chuyển từ CAS Proxy sang OAuth2 cần chọn đúng mục tiêu: đăng nhập người dùng, máy–máy không có người dùng, gọi API **on behalf of** user, hay chỉ duy trì ứng dụng CAS cũ. Mỗi mục tiêu có grant, trust boundary và chính sách khác nhau.

Bài thuộc **Spring Security – federation → CAS Proxy**, trình bày cơ chế giao thức, điểm giống/khác, cách đánh giá kiến trúc, các phương án **giữ CAS**, **chạy song song**, **dùng cầu nối có kiểm chứng**, **OAuth2/OIDC mới** và **RFC 8693 Token Exchange** khi được hỗ trợ, cùng ví dụ Spring Security, Java 17, ma trận kiểm thử và runbook chuyển đổi.

## 1. Bài toán thực tế: Portal gọi Billing API thay người dùng

Giả sử nhân viên **Lan** đăng nhập vào Portal A và chọn “Xem hóa đơn”. Portal cần gọi Billing B và Billing phải quyết định Lan có quyền xem dữ liệu hay không.

~~~text
Browser của Lan
       |
       | Đăng nhập và xem hóa đơn
       v
   Portal A
       |
       | Gọi thay mặt Lan
       v
   Billing API B
       |
       v
  Kiểm tra quyền:
   - Lan là ai?
   - Portal A có được phép làm đại diện không?
   - Ticket/token dành cho Billing B?
   - Được đọc hóa đơn nào của tenant nào?
~~~

Trong mô hình CAS cũ, Portal có **PGT**, xin **PT-B** rồi gọi Billing. Billing dùng CAS Server để **proxyValidate PT-B**. Trong kiến trúc OAuth2, Portal thường nhận/đổi lấy **access token dành riêng cho Billing**, Billing xác minh token và áp domain authorization.

Cả hai đều có thể cung cấp danh tính người dùng nhưng **không tự bảo đảm quyền xem mọi hóa đơn**. Quyền trên resource và tenant vẫn thuộc ứng dụng/API.

## 2. Bốn vai trò của CAS và bốn vai trò của OAuth2

| CAS | OAuth2 | Lưu ý |
| --- | --- | --- |
| CAS Server | Authorization Server hoặc OP trong hệ thống OAuth/OIDC | Vai trò có thể được một sản phẩm cung cấp, nhưng giao thức khác |
| User/browser | Resource Owner và user agent | Không phải mọi OAuth2 flow đều có user |
| Portal A, CAS Client/Proxy | OAuth Client | Có thể là confidential client/BFF |
| Billing B, CAS Client | Resource Server | B kiểm tra chứng cứ nhận được theo đúng protocol |
| PGT | Không có mapping 1-1 chuẩn | Dùng xin nhiều PT cho target services |
| PT | Access Token **không tương đương** | PT là ticket one-time validation; OAuth token có lifecycle/token type khác |
| CAS proxy chain | OAuth actor/delegation context khi AS hỗ trợ | Không có mapping tự động |
| CAS service identifier | OAuth resource/audience | Gần về ý tưởng “đích”, nhưng semantics và validation khác |
| CAS principal attributes | OAuth token claims/scopes/entitlements | Không được tự sao chép raw attributes thành permissions |
| CAS TGT/TGC | OIDC/AS session/refresh token **không tương đương** | Không có phép đổi trực tiếp chỉ bằng tên |

**OIDC** là lớp authentication trên OAuth2, cung cấp **ID Token** và các quy tắc nhận dạng `(iss, sub)`. **OAuth2 tự thân không bảo đảm xác thực người dùng theo cách ID Token OIDC làm**. Khi hiện đại hóa **đăng nhập web**, thường xem xét OIDC; khi hiện đại hóa **gọi API**, dùng OAuth2 access tokens.

## 3. CAS Proxy hoạt động như thế nào?

CAS Server xác thực người dùng một lần. Khi Portal A xác minh Service Ticket (**ST**) với CAS, nó có thể yêu cầu PGT bằng một **pgtUrl HTTPS callback** đã được CAS tin cậy. CAS gửi **pgtId** và **pgtIou** qua callback, rồi cung cấp PGTIOU trong response validation để A ghép đúng PGT.

Về sau:

1. Portal A gọi CAS `/proxy` với **PGT** và **targetService=Billing B**.
2. CAS kiểm tra PGT/service policy và cấp **PT-B**.
3. A chuyển **PT-B** tới Billing B.
4. Billing B gọi CAS `/proxyValidate` cùng `ticket=PT-B` và **service=B**.
5. CAS kiểm tra ticket còn hạn, đúng service, proxy chain và chính sách tương ứng, rồi trả kết quả validation.
6. Billing dùng kết quả đã xác minh để tạo Authentication và xét quyền local.

~~~text
Browser        Portal A                  CAS Server               Billing B
   |              |                          |                         |
   | Login -------|--- ST validation ------->|                         |
   |              |<-- Assertion + PGTIOU ---|                         |
   |              |<-- PGT qua pgtUrl -------|                         |
   |              |                          |                         |
   | Xem hóa đơn->|                          |                         |
   |              |--- /proxy(PGT,B) ------->|                         |
   |              |<-- PT-B -----------------|                         |
   |              |--- API request + PT-B ---------------------------->|
   |              |                          |<-- /proxyValidate ------|
   |              |                          |--- validated identity ->|
   |              |<--------------- API response ---------------------|
~~~

**PGT có thể cấp nhiều PT; mỗi PT được gắn với một target service.** Theo CAS protocol, PT có **one-time validation** tương tự ST. CAS Server có thể trả **proxy chain** để Billing quyết định có chấp nhận A làm proxy hay không.

### Phân biệt ST, PT và PGT

| Loại | Dùng ở đâu? | Đặc trưng |
| --- | --- | --- |
| ST | Browser SSO tới một service | One-time validation, service-bound |
| PT | A gọi B thay user | One-time validation, service-bound, có proxy context |
| PGT | A xin các PT mới | Có thể dùng nhiều lần, cần bảo vệ như credential quan trọng |
| TGT/TGC | Phiên SSO tại CAS/browser | Không được đưa thẳng tới Billing như API credential |
| CasAuthenticationToken cached | State cục bộ ở B | Có thể tái dùng kết quả đã xác thực nếu Spring StatelessTicketCache bật |

**CAS Proxy có yếu tố ủy nhiệm nhưng không phải OAuth2 authorization grant.** Nó mang thông tin user và đường đi proxy; những quyền business như “invoice.read cho tenant north” phải được CAS policy, SP mapping và đặc biệt **Billing domain authorization** giải quyết.

## 4. OAuth2 giải quyết bài toán khác ra sao?

OAuth2 phân tách rõ các vai trò:

- **Resource Owner:** người dùng hoặc chủ thể có quyền cho phép dùng tài nguyên; trong một số flow không cần user tham gia trực tiếp.
- **Client:** ứng dụng muốn truy cập tài nguyên, ví dụ Portal A.
- **Authorization Server:** hệ thống quyết định và phát access token.
- **Resource Server:** Billing B, nơi xác minh token và bảo vệ hóa đơn.

Một access token thường được dùng như sau:

~~~text
User/Portal A            Authorization Server              Billing B
      |                           |                              |
      | Authorization grant      |                              |
      |-------------------------->|                              |
      |<----- Access Token -------|                              |
      |                           |                              |
      |--- Authorization: Bearer ACCESS_TOKEN ------------------>|
      |                           |             Verify token and policy
      |<--------------------------- API data / 401 / 403 ---------|
~~~

**OAuth2 Access Token không bắt buộc là JWT.** Nó có thể là opaque token được introspect hoặc JWT ký số với các claims như `iss`, `aud`, `exp`, `scope` theo profile phù hợp. Đối với JWT access tokens theo **RFC 9068**, Resource Server cần kiểm loại token/phạm vi issuer/audience, chứ không chấp nhận mọi JWT có chữ ký hợp lệ.

**OAuth2 grant không đồng nghĩa OAuth2 scope:** grant mô tả **cách client nhận token**; scope mô tả **quyền phạm vi yêu cầu/cấp**; audience/resource mô tả **nơi token được dùng**. Các ràng buộc này bổ sung nhau, không thay thế authorization tại Billing.

## 5. Bảng phân biệt toàn diện CAS Proxy và OAuth2

| Khía cạnh | CAS Proxy (PGT/PT) | OAuth2 |
| --- | --- | --- |
| Mục tiêu cốt lõi | Ủy nhiệm **authentication** giữa CAS clients/services | **Delegated access/authorization** cho protected resources |
| Chứng cứ gửi API | Proxy Ticket | OAuth2 Access Token |
| Bên phát | CAS Server | Authorization Server |
| Đăng nhập người dùng | CAS SSO | Thường OIDC nếu RP cần xác thực user |
| Đích nhận | `targetService`/CAS service identifier | `aud`/resource indicator và client/scope policy |
| Cấp vé/token | `/proxy` bằng PGT | Token endpoint theo grant phù hợp |
| Kiểm chứng tại B | `/proxyValidate` với CAS | JWT local verification hoặc introspection |
| Tái dùng | PT one-time validation; Spring cache có thể tái dùng **kết quả auth** | Access token thường dùng nhiều request tới audience hợp lệ trong lifetime |
| Ngữ cảnh acting party | CAS proxy chain | Client identity; actor/`act` khi token exchange hỗ trợ |
| Quyền chi tiết | CAS service/access policies + ứng dụng tự kiểm | Scopes/claims/policies + ứng dụng tự kiểm |
| Consent | Không có tiêu chuẩn OAuth consent trong PT | Authorization có thể gắn user consent hoặc enterprise policy; **không bắt buộc UI consent mọi flow** |
| Thu hồi | CAS ticket/session policies; app local session/cache riêng | Token revocation, introspection, JWT TTL, AS/RS policy |
| M2M không có user | CAS proxy không phải lựa chọn tự nhiên | `client_credentials` thích hợp |
| Web login hiện đại | CAS login vẫn dùng được | OIDC Authorization Code + PKCE phù hợp |
| Chuỗi ủy nhiệm nhiều hop | CAS proxy chain | RFC 8693 token exchange/`act` khi AS hỗ trợ |
| Triển khai trong Spring | `spring-security-cas` | `oauth2Login`, `oauth2Client`, `oauth2ResourceServer` |
| Chuyển đổi | Không có conversion tự động chuẩn PT → Access Token | Cần AS/broker/gateway có trust và policy để phát token mới |

**Điểm giống:** cả hai đều cần HTTPS, trust configuration, chống dùng sai target và authorization tại service. **Điểm khác quan trọng nhất:** PT chứng minh được một ngữ cảnh xác thực/proxy với CAS, còn access token là artifact đại diện cho một **quyết định cấp quyền** trong hệ OAuth2.

## 6. “Ủy quyền” có ba nghĩa không được trộn

Trong hệ thống kỹ thuật, chữ **ủy quyền** có thể dùng cho ba việc:

1. **Proxying authentication:** A chứng minh với B rằng mình đang đại diện một user đã được CAS xác thực. Đây là trọng tâm CAS Proxy.
2. **Delegated authorization:** Resource Owner/AS cấp cho A quyền gọi B trong phạm vi đã cho. Đây là một mẫu điển hình của OAuth2.
3. **Business authorization:** Billing quyết định user/actor có quyền xem hóa đơn số 37 của tenant north hay không. Đây là quyết định của ứng dụng.

Ví dụ:

~~~text
CAS:
  "Lan đã được CAS xác thực; yêu cầu đến qua proxy Portal A."

OAuth2:
  "Portal A được AS cấp access token dành cho Billing,
   scope=invoice.read, subject=Lan, actor=A nếu có delegation."

Billing:
  "Hóa đơn 37 thuộc tenant north và Lan có membership hợp lệ,
   Portal A nằm trong tập proxy/client được chấp nhận;
   cho phép đọc, không cho phép sửa."
~~~

Đừng lấy thông tin “đăng nhập hợp lệ” thay cho “đã được cấp phép xem tất cả”, hoặc dùng client identity máy–máy thay người dùng mà không khai báo rõ mô hình.

## 7. Subject, client và actor: ai thực sự đang hành động?

Trong CAS Proxy, validation response có principal người dùng và có thể có **proxy chain**. Backend kiểm chứng user và chuỗi proxy được phép.

Trong OAuth2, ít nhất cần phân biệt:

- **`sub`**: subject của access token, có thể là người dùng hoặc client tùy loại token/profile.
- **`client_id` / `azp`**: danh tính client liên quan, khi AS/profile phát các claims đó.
- **`aud`**: Resource Server mà token dành cho.
- **`scope`**: quyền/phạm vi mà token được cấp.
- **`act`**: cấu trúc biểu diễn acting party trong token exchange khi AS quyết định phát token delegation dạng composite.
- **`tenant`**: custom business claim theo contract, **không mặc định là bằng chứng membership hiện hành**.

Ví dụ **JWT access token minh họa** từ một AS đã tin cậy:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-57",
  "aud": ["billing-api"],
  "client_id": "portal-client",
  "scope": "invoice.read",
  "act": { "sub": "portal-service" },
  "tenant": "north",
  "exp": 1794045600
}
~~~

Payload trên **không có chữ ký và không phải token dùng được**. Trường `act` là đặc trưng của RFC 8693 khi áp dụng, **không bắt buộc trong mọi access token**; `tenant` do tổ chức tự định nghĩa. Backend chỉ tin các claims sau khi đã xác minh token, issuer/audience/expiry và chính sách của mình.

**Chú ý `sub` của access token client_credentials có thể là client**, không phải người dùng. Không lấy M2M token rồi âm thầm thực thi nghiệp vụ “thay Lan” chỉ vì tên client là portal.

## 8. CAS targetService và OAuth audience/resource

CAS Proxy:

~~~text
CAS /proxy?pgt=PGT-...&targetService=https://billing.example.test/cas
    -> CAS cấp PT cho đúng targetService.
Billing /proxyValidate?service=https://billing.example.test/cas&ticket=PT-...
    -> CAS đối chiếu đúng service.
~~~

OAuth2:

~~~text
AS phát access token:
  aud = billing-api
  scope = invoice.read

Billing:
  verify token
  require aud contains billing-api
  require scope contains invoice.read
  verify tenant + invoice ownership
~~~

**`targetService` và `aud` không tự chuyển đổi được.** Khi migration, phải có bảng mapping được phê duyệt từ CAS service URLs tới OAuth resource identifiers. Không chỉ bỏ hostname/path rồi suy ra audience một cách heuristic.

Với nhiều APIs, **RFC 8707 Resource Indicators** giúp client báo resource cần truy cập bằng tham số `resource` khi AS hỗ trợ. **RFC 9068** đặt yêu cầu phân biệt access tokens dành cho từng resource bằng audience. Một access token cho Billing không nên được Payroll hoặc Admin API chấp nhận.

## 9. CAS proxy chain và OAuth delegation chain

CAS proxy validation có thể trả thông tin các proxies tham gia:

~~~text
User Lan -> Portal A -> Aggregator C -> Billing B
             |              |
          Proxy A         Proxy C

CAS proxy chain: theo thông tin CAS đã xác minh
Billing quyết định có chấp nhận chuỗi A,C không.
~~~

OAuth2 **Token Exchange (RFC 8693)** đưa vào thuật ngữ `subject_token`, `actor_token` và `act` claim nhằm biểu diễn việc một actor hành động thay subject. AS có quyền từ chối yêu cầu hoặc phát token với phạm vi hẹp hơn.

**Không có phép chuyển đổi mặc định CAS proxy chain → `act` chain.** Một AS/broker cần quy định cách xác minh CAS source, danh tính proxies, quyền delegation và mapping identifiers. Các trường hợp dùng nhiều tầng phải kiểm tra không mất acting-party provenance và ngăn impersonation vượt quyền.

**Impersonation khác delegation:** một token chỉ nói người dùng Lan có thể che mất việc Portal A đang thực hiện thao tác. Nếu chính sách kiểm toán hoặc separation-of-duties yêu cầu biết actor, hãy dùng cơ chế delegation/token exchange có chứng cứ, không tự tạo token có mỗi `sub=Lan` rồi bỏ thông tin actor.

## 10. CAS Proxy có “scope” không?

CAS có **Service Registry, access strategy, attribute release và proxy policies** để kiểm soát service nào được phát/kiểm PT, proxy chain nào được tin và thuộc tính nào được trả. Đây là các biện pháp authorization ở CAS Server.

Tuy nhiên, một CAS PT **không phải OAuth2 access token** và không có claim **`scope` chuẩn OAuth2** theo nghĩa “invoice.read, invoice.write” do AS phát và RS kiểm. CAS có thể gửi principal attributes để ứng dụng tự map sang roles nhưng không có nghĩa PT tự mang quyền chi tiết.

Chuyển đổi phải thiết kế rõ:

| Nguồn CAS | Đích OAuth2/ứng dụng | Quy tắc |
| --- | --- | --- |
| CAS service identifier Billing | OAuth audience `billing-api` | Mapping allowlist bởi security owner |
| CAS proxy A | OAuth client/actor `portal-service` | Xác minh proxy chain và client identity |
| CAS principal `user-57` | OAuth subject `user-57` hoặc ID nội bộ | Account linking có bằng chứng, không dựa email |
| CAS group `billing-viewers` | Scope `invoice.read` | Không tự sao chép; giới hạn theo policy và tenant |
| CAS authentication context | OAuth `acr`/`amr` hoặc custom assurance | Chỉ khi có contract và AS thực sự xác minh |
| CAS TGT/PGT lifetime | Token `exp` và revocation | Không thể suy ra thời hạn một-một |
| CAS SLO | OAuth token revocation/session logout | Cần triển khai riêng |

**Quy tắc quyền tối thiểu:** Token mới chỉ được cấp quyền nằm trong **giao của** quyền user, quyền của client/actor, policy CAS delegation đã xác minh, resource và tenant được cho phép.

## 11. OAuth grant nào thay thế tình huống nào?

| Nhu cầu thực tế | Lựa chọn thường hợp lý | Không nên dùng |
| --- | --- | --- |
| Browser vào Portal và cần SSO | **OIDC Authorization Code + PKCE**; giữ CAS nếu hệ legacy | `client_credentials` thay cho xác thực user |
| Portal có user context và gọi Billing thay user | OAuth2 access token dành cho Billing; **Token Exchange RFC 8693** nếu AS hỗ trợ | M2M token giả là user token |
| Cron job Billing đồng bộ dữ liệu không có user | OAuth2 `client_credentials` | CAS PT cần giả mạo người dùng |
| Backend B chỉ tin CAS PT và chưa thể đổi | **Giữ CAS Proxy** hoặc gateway/adapter | Đưa JWT trực tiếp vào `/proxyValidate` |
| User có CAS login, API mới dùng OAuth | OIDC federation/AS hoặc trusted bridge có validation | “JWT ký bằng khóa tùy ý” do Portal tự tạo |
| Hệ thống có nhiều hops A→C→B | Token exchange có `act`/policy hoặc CAS proxy chain trong giai đoạn legacy | Bỏ mất identity của actor trung gian |
| Cần thu hồi quyền gần tức thì | Opaque token introspection, token TTL ngắn + revocation checks | JWT dài hạn không có revocation |
| Mobile/native app login | Authorization Code + PKCE, browser hệ thống | Password grant / Embedded browser không cần thiết |
| Third-party delegation theo resource owner | OAuth2 AS policy + consent/contract + resource scoping | CAS proxy chain như thay thế consent OAuth |

**Consent** có thể là màn hình cho người dùng chấp thuận hoặc chính sách ủy quyền nội bộ theo AS; OAuth2 **không bắt buộc mọi token phải có một popup consent**. Client credentials không biểu diễn user consent.

## 12. Quyết định giữ CAS Proxy khi nào?

**Giữ CAS Proxy là phương án hợp lý** khi:

- Chỉ có một tập nhỏ services lâu đời, giao thức và CAS integration đang được kiểm soát.
- CAS Server và Java CAS clients vẫn được duy trì, security patches và service registry được quản trị.
- Các downstream APIs yêu cầu **proxy chain**, không có OAuth AS tin cậy hoặc migration cần nhiều thay đổi.
- User session lifecycle đang gắn chặt với CAS và không có yêu cầu M2M/đối tác mới.
- Hệ thống có đủ khả năng giám sát PT/PGT, TTL, SLO và authorization theo service.
- Chi phí chuyển đổi và rủi ro vận hành vượt lợi ích trước mắt.

Cần bổ sung các guardrails:

1. Không chấp nhận mọi proxy chain; cấu hình **allowedProxyChains**, không bật `acceptAnyProxy=true` chỉ để khỏi lỗi.
2. CAS PGT chỉ lưu server-side, bảo vệ secret store và pgtUrl callback.
3. PT được cấp cho đúng targetService, `/proxyValidate` qua HTTPS.
4. Xác minh người dùng và local entitlements tại Billing.
5. Nếu Spring `StatelessTicketCache` tái dùng Authentication, đặt TTL, scope và revocation riêng; đừng lẫn với one-time validity của PT ở CAS.
6. Thu hồi quyền/session phải có SLO hoặc backend revocation policy, không chỉ chờ CAS TGT hết hạn.
7. Lên kế hoạch nâng cấp dependency CAS Client/Spring Security và thay thế nếu hệ legacy hết hỗ trợ.

**Giữ CAS không có nghĩa dừng cải thiện an ninh**, cũng không phải “kém OAuth” trong mọi use case. Quyết định phụ thuộc yêu cầu khả năng, trust và chi phí.

## 13. Chuyển M2M không có người dùng sang client_credentials

Khi một batch service gọi API với **danh tính ứng dụng**, không có resource owner đang hoạt động, OAuth2 **Client Credentials Grant** phù hợp hơn CAS Proxy.

~~~text
Job A           Authorization Server             API B
 |                    |                            |
 | -- client auth --->|                            |
 | <--- token --------|                            |
 |                   aud=B,scope=report.write      |
 | -- Bearer token -------------------------------->|
 |                                verify client, audience, scope
~~~

AS xác thực client A bằng client secret/private_key_jwt/mTLS hoặc phương thức phù hợp, áp access policy rồi cấp token dành cho B.

**Không được biến client_credentials thành user impersonation ngầm**. Nếu B cần biết “Lan duyệt hóa đơn” hoặc cần kiểm quyền của Lan, client_credentials **không mang bằng chứng user đã ủy quyền theo một flow user-centric**.

Đối với dữ liệu do service quản trị theo chính sách riêng, B có thể kiểm **client identity + machine scope + tenant/service ownership**, hoàn toàn không cần lấy username giả.

## 14. Đăng nhập web mới bằng OIDC Authorization Code + PKCE

Nếu mục tiêu là đổi **đăng nhập web** từ CAS sang giao thức hiện đại, thường dùng **OIDC Authorization Code Flow** (với PKCE theo RFC 9700), không chuyển Service Ticket CAS thành Access Token trong browser.

~~~text
Browser
    |
    v
Portal Web / Spring Security oauth2Login
    |
    v
OIDC Provider / Authorization Server
  authenticate user
  authorization code + PKCE/state/nonce
    |
    v
Portal backend receives code
  exchanges at token endpoint
  validates ID Token iss/aud/exp/nonce/signature
    |
    v
Portal local session + verified identity link
    |
    v
OAuth Access Token for APIs (when authorized)
~~~

**ID Token để xác thực RP**, còn **Access Token để gọi protected APIs**. Không gửi ID Token cho Billing như Access Token. User identity từ OIDC được gắn với **`iss,sub`**, không dùng email làm primary key liên kết tài khoản.

Nếu doanh nghiệp muốn vẫn dùng giao diện đăng nhập CAS, có thể cấu hình một **OIDC Provider/Broker** dùng CAS/LDAP/SAML upstream làm nguồn xác thực, rồi phát OIDC tokens cho clients mới. Điều này phụ thuộc module/khả năng thật của sản phẩm IdP; không tự cho rằng mọi CAS Server tự trở thành OP chỉ vì bật một flag ở Portal.

## 15. On-behalf-of (OBO) với OAuth2 Token Exchange RFC 8693

Khi Portal A **đã có user token hợp lệ** và cần gọi Billing B, có thể yêu cầu AS phát token mới **dành cho Billing**, với quyền hẹp hơn và actor metadata khi AS hỗ trợ **Token Exchange**.

Ví dụ **minh họa** về POST token endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_AUTH

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=SIGNED_OR_OPAQUE_USER_ACCESS_TOKEN
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&audience=billing-api
&scope=invoice.read
~~~

Trong triển khai delegation cần actor explicit, request có thể thêm `actor_token` và `actor_token_type` nếu AS hỗ trợ; nhiều AS có thể dùng client authentication để xác định actor theo chính sách riêng. **Token exchange không mặc định trả claim act hoặc luôn mang đúng semantics delegation**: AS có quyền quyết định phát token, giảm scope, thể hiện actor/subject hoặc từ chối.

Ví dụ payload **access token đầu ra** sau AS policy:

~~~json
{
  "iss": "https://auth.example.test",
  "aud": ["billing-api"],
  "sub": "user-57",
  "act": { "sub": "portal-service" },
  "scope": "invoice.read",
  "tenant": "north",
  "exp": 1794045600
}
~~~

Đây là **mẫu dữ liệu chưa ký**. Billing phải kiểm token và domain authorization, không tin các claims chỉ vì nhìn giống JSON ví dụ.

### Những giới hạn phải hiểu rõ

- **Token Exchange là extension**; không phải AS nào cũng có.
- AS **phải kiểm tra** input token theo token type; actor token (nếu có) cũng phải được kiểm chứng.
- Client phải được **đăng ký và cho phép exchange** theo chính sách.
- `subject_token` không đồng nghĩa CAS PT. **RFC 8693 không chuẩn hóa việc lấy CAS PT bất kỳ làm input token được tất cả AS nhận**.
- Token đầu ra có lifetime/revocation riêng. Theo RFC 8693, exchange **không tự tạo quan hệ ràng buộc thu hồi** hai chiều giữa input/output tokens.
- Nếu user và actor cần accountability, AS/RS phải đồng thuận cách thể hiện `act` và kiểm soát delegation.
- Không dùng `client_credentials` rồi tự chép `sub=Lan` vào JWT để giả OBO.

## 16. Phương án cầu nối CAS → OAuth2: cần một trust boundary minh bạch

Nhiều tổ chức không thể thay tất cả CAS clients một lúc. Khi đó có thể tạo **trusted bridge** để xác minh CAS trước rồi nhờ **AS thực thụ** cấp access token mới.

~~~text
Legacy Portal A
    |
    | CAS Proxy Ticket PT-BRIDGE
    v
Trusted CAS Validation Bridge
    | 1. CAS /proxyValidate với service đúng
    | 2. Kiểm proxy chain, principal, TTL, policies
    | 3. Map verified CAS identity sang local account
    | 4. Xác định client/tenant/resource quyền yêu cầu
    | 5. Chuyển authenticated evidence qua kênh AS tin cậy
    v
OAuth2 Authorization Server
    | Kiểm bridge identity, client policy,
    | cấp token mới aud=Billing, scope hẹp
    v
OAuth Access Token
    |
    v
Billing Resource Server
    | JWT verification/introspection + business authorization
~~~

**Cầu nối không được là “API ký JWT từ chuỗi CAS username”.** Nó phải là một thành phần được AS tin cậy, có source validation, service binding, actor identity và audit. Tài liệu kiến trúc phải nêu ai là token issuer, ai sở hữu signing keys, ai xét scope/tenant, ai thu hồi token.

### Khi bridge có thể cấp token?

Chỉ sau khi:

1. CAS PT được xác minh **một lần** với CAS Server cho **đúng bridge service ID**.
2. Proxy chain/PGT path của Portal được cho phép và principal đã được xác thực.
3. Subject được ánh xạ sang local account từ nguồn đáng tin, không dựa vào email chưa được xác minh.
4. Client Portal chứng minh identity server-to-server (mTLS/private key hoặc cơ chế phù hợp).
5. AS kiểm policy user+actor+resource+tenant+requested scope.
6. Token được phát **bởi AS có trách nhiệm**, chứa audience/lifetime phù hợp và metadata delegation khi được hỗ trợ.
7. Bridge ghi correlation/audit không có raw PT/PGT/access token.
8. Có revocation/expiry policy và phương án fail closed khi CAS/AS không sẵn sàng.

**Không tự nhận bất kỳ CAS ST/PT làm RFC 8693 subject_token_type chuẩn.** Nếu AS hỗ trợ một custom token type/extension cho CAS, đó là **thỏa thuận riêng**, phải có validator, namespace, threat model và tests. Phương án đơn giản hơn nhiều khi có thể là user reauthentication qua OIDC broker và cấp OAuth tokens đúng flow.

## 17. Chọn cầu nối hay đăng nhập lại qua OIDC?

| Tiêu chí | CAS→OAuth bridge | OIDC sign-in mới |
| --- | --- | --- |
| Thay đổi frontend legacy | Có thể nhỏ hơn | Có thể phải sửa login/callback/logout |
| Nguồn user session | CAS | OIDC OP/broker |
| AS biết CAS identity bằng cách nào? | Trusted validation/mapping/bridge contract | OIDC authentication trực tiếp hoặc qua broker |
| User phải đăng nhập lại? | Không nhất thiết, nếu CAS session hợp lệ và policy cho phép | Có thể SSO nếu broker dùng upstream CAS, tùy cấu hình |
| Authorization API | OAuth access token mới | OAuth access token mới |
| Rủi ro | Bridge trở thành điểm quyền lực lớn, token minting/broker mapping | Migration identities/sessions/redirects/phía user |
| Vòng đời trung hạn | Tăng phức tạp vận hành hai giao thức | Dễ thống nhất client ecosystem |
| Nên chọn khi | Cần chuyển từng backend, legacy portal khó sửa | Có khả năng chuyển clients và IdP/broker phù hợp |

**Tầm nhìn dài hạn:** nếu mục tiêu là API ecosystem đa client, OIDC/OAuth2 có thể đơn giản hóa semantics grant/scope/audience hơn. **Ngắn hạn:** bridge có ích nếu CAS là nguồn authentication duy nhất và phải bảo toàn service cũ. Đừng duy trì bridge mãi mà không có owner/review, vì nó thêm trust boundary và logic migration khó bảo trì.

## 18. Chuyển đổi theo lớp: authentication, API token, authorization

Không nhất thiết phải đổi ba lớp cùng một lúc.

**Lớp 1 — Authentication:** CAS login → OIDC login khi thích hợp, giữ account link cũ trong giai đoạn chuyển tiếp.

**Lớp 2 — Service-to-service credential:** CAS PT/PGT → OAuth access token cấp cho Billing, có client authentication và audience.

**Lớp 3 — Business authorization:** group/attribute CAS → app roles/entitlements/resource policies; không bê nguyên roles giữa hai giao thức.

~~~text
Trước:
 CAS login -> Portal session -> PGT/PT -> Billing CAS validation
                                 |
                          CAS groups -> local roles

Trong giai đoạn song song:
 CAS/OIDC login -> Local account identity link
                     |
               trusted bridge / AS
                     |
              OAuth access token -> Billing Resource Server
                     |
              local entitlements, tenant checks

Sau:
 OIDC login -> OAuth2 Client -> AS/token exchange -> Billing OAuth2 RS
                                              |
                                        domain authorization
~~~

**Không nhầm “access token được cấp” với “user đã được cấp quyền”.** Dù token có `scope=invoice.read`, Billing vẫn phải kiểm invoice thuộc tenant hợp lệ và user còn quyền.

## 19. Ma trận lựa chọn kiến trúc

| Điều kiện chủ đạo | Hướng ưu tiên | Lý do |
| --- | --- | --- |
| Chỉ có Portal↔Billing legacy, ít thay đổi, không cần external APIs | **Giữ CAS Proxy** có hardening | Ít rủi ro thay đổi, CAS flow đang giải quyết bài toán |
| APIs mới có nhiều clients/đối tác | **OAuth2 Resource Server** | Standard access token, scope/audience và client policy |
| Máy–máy không có user | **client_credentials** | Danh tính máy và quyền máy rõ ràng |
| User hành động qua nhiều backends | **OAuth2 user delegated token / Token Exchange** | Audience hẹp, subject+actor khi cần |
| Chưa thể sửa Portal nhưng Billing cần OAuth | **Trusted CAS→OAuth bridge** | Bảo toàn CAS login tạm thời, đổi dần backend |
| Đang xây ứng dụng browser mới | **OIDC Authorization Code + PKCE** | Authentication chuẩn, identity mapping rõ |
| Cần tách nhiều hop ủy nhiệm và audit actor | **RFC 8693 khi AS hỗ trợ**, hoặc giữ CAS proxy tạm thời | Cần actor lineage và policy |
| Chưa có AS thật, ngân sách hạn chế | **Không tự chế AS/token service** | Thà giữ CAS được bảo vệ còn hơn OAuth giả |
| Cần thu hồi API rất nhanh | **Opaque token introspection/short JWT TTL + revocation** | Kiểm soát freshness; yêu cầu thiết kế cache |
| Có rủi ro account/tenant mapping | **Hoãn cutover quyền**, xử lý identity migration trước | Tránh takeover và cross-tenant access |

Một quyết định tốt cần đánh giá **security, compatibility, change cost, developer experience, observability, outage modes và vận hành lâu dài**, không chỉ “OAuth2 hiện đại hơn”.

## 20. Spring Security: CAS Client so với OAuth2 Client/Resource Server

Trong Spring Security Servlet:

| Thành phần CAS | Thành phần OAuth2/OIDC | Chức năng |
| --- | --- | --- |
| `CasAuthenticationFilter` | `OAuth2LoginAuthenticationFilter`, `BearerTokenAuthenticationFilter` | Nhận credential/response theo protocol |
| `CasAuthenticationProvider` | OAuth2/OIDC authentication provider hoặc JWT/opaque provider | Kiểm chứng protocol |
| `Cas20ProxyTicketValidator` | `JwtDecoder` hoặc `OpaqueTokenIntrospector` | Backend validation |
| `ServiceProperties.service` | OAuth resource identifier / `aud` | Đích phải khớp |
| `AuthenticationUserDetailsService` | `OidcUserService`, `JwtAuthenticationConverter` | Identity/authorities mapping |
| `StatelessTicketCache` | Access token validation/cache policies | Lifecycle khác; không dùng chung cache |
| `spring-security-cas` | `spring-security-oauth2-client`, `spring-security-oauth2-resource-server` | Dependencies khác |

**Mấu chốt:** `oauth2ResourceServer` bảo vệ **API nhận Bearer token**, `oauth2Client` giúp một app **nhận và sử dụng token để gọi API khác**, còn `oauth2Login` dùng OIDC/OAuth provider login. Chúng không tự động dựng một **Authorization Server**. Để phát token dùng được, cần một AS/OP riêng có policy và key management thực tế.

Khi chuyển đổi, không thay `saml2Login` hoặc `casAuthenticationFilter` bằng `oauth2ResourceServer` rồi mong người dùng browser tự đăng nhập. Đây là **những security flows khác nhau**.

## 21. Spring Boot 3 / Spring Security 6: Billing nhận JWT Access Token

Một Billing API mới có thể được cấu hình làm OAuth2 Resource Server. Ví dụ với **Spring Boot 3.x, Spring Security 6.x, Java 17+**, sử dụng dependencies Spring Web, Spring Security và `spring-boot-starter-oauth2-resource-server`.

**application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://auth.example.test"
          audiences: "billing-api"
~~~

Hai properties này yêu cầu token JWT có **issuer** và **audience** phù hợp theo cơ chế Spring Boot. Các hostname ví dụ chỉ để hiểu cấu hình; hệ thống thực cần AS metadata, JWKS và tokens hợp lệ.

**SecurityFilterChain của Billing**:

~~~java
package com.example.billing.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class BillingApiSecurityConfig {

    @Bean
    SecurityFilterChain billingApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoice.read")
                .requestMatchers(HttpMethod.POST, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoice.write")
                .anyRequest().authenticated())
            .sessionManagement(sessions -> sessions
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Đây là class thuộc một ứng dụng Spring Boot**, không chạy bằng `javac` thuần JDK. Nó chỉ xác thực JWT và kiểm **scope theo HTTP method/path** trong `/api/**`. Nó **chưa thực thi** tenant membership, user/actor distinction, object ownership, separation-of-duties và revocation freshness—các kiểm tra đó phải nằm ở domain service/authorization layer.

Spring Security mặc định thường ánh xạ JWT `scope`/`scp` sang authorities có prefix **`SCOPE_`**. Nếu AS dùng claim khác, cần `JwtAuthenticationConverter` được kiểm soát. Không map mọi claim `groups` thành `ROLE_ADMIN` hoặc tin một `tenant` do client tự truyền.

**CSRF:** nếu API chỉ nhận Bearer tokens trong Authorization header và không dùng session cookies, có thể thiết kế CSRF policy riêng. Không tắt CSRF toàn site nếu cùng ứng dụng vẫn có browser sessions/cookies.

## 22. Opaque token + introspection: khi revocation là trọng tâm

Không phải mọi access token đều là JWT. Một số doanh nghiệp muốn Backend B hỏi AS về trạng thái active khi nhận request; OAuth **Token Introspection (RFC 7662)** là một lựa chọn phù hợp.

**Spring Boot YAML (phương án thay thế JWT)**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: "https://auth.example.test/oauth2/introspect"
          client-id: "${BILLING_INTROSPECTION_CLIENT_ID}"
          client-secret: "${BILLING_INTROSPECTION_CLIENT_SECRET}"
~~~

**Không bật đồng thời cả hai ví dụ như một mặc định tự động nhận mọi credential.** Quyết định token format, issuer, target API và policy trước.

| JWT verification | Opaque introspection |
| --- | --- |
| RS kiểm chữ ký/exp/iss/aud thường không cần gọi AS mỗi request | RS hỏi AS/endpoint introspection về token active |
| Thích hợp chịu tải cao, offline verification | Thường thuận tiện khi cần thu hồi nhanh |
| Phải thiết kế revocation cho JWT chưa hết hạn | Độ tươi phụ thuộc AS/introspection/cache policy |
| Quản lý JWK rotation, allowed alg và cross-JWT confusion | Quản lý introspection client secrets, TLS và AS availability |
| Token có thể chứa claims lộ nếu bị giải mã | Opaque token không lộ claims trực tiếp qua chuỗi |
| Phải kiểm quyền theo domain tương tự | Phải kiểm quyền theo domain tương tự |

**Nếu cache introspection responses**, khả năng revoke nhanh cũng có độ trễ bằng TTL cache; không hứa “thu hồi tức thì” khi cache còn hiệu lực.

## 23. Spring OAuth2 Client: Portal gọi Billing ra sao?

Portal đóng vai **OAuth2 Client** để lấy access token rồi đặt header:

~~~http
GET /api/invoices/37 HTTP/1.1
Host: billing.example.test
Authorization: Bearer OAUTH_ACCESS_TOKEN
~~~

Spring Security có **`OAuth2AuthorizedClientManager`** và các tích hợp RestClient/WebClient giúp chọn authorized client và bổ sung Bearer token cho outbound requests. Token manager có thể xử lý authorization_code, client_credentials và refresh theo provider/config phù hợp.

**Nhưng:** công cụ tiện dụng này **không tự biến một CAS authentication thành OAuth user delegation**. Khi Portal vừa dùng CAS login vừa gọi Billing:

- Nếu chỉ cần machine identity: có thể cấu hình **client_credentials** cho Portal.
- Nếu cần user-delegated access: phải có **user token/authorization grant hoặc token exchange** được AS chấp nhận, hoặc trusted bridge.
- Nếu AS chưa hỗ trợ CAS federation, **đừng giả rằng client_credentials token có chủ thể Lan**.
- Nếu dùng `setDefaultOAuth2AuthorizedClient(true)`, hiểu rằng mọi request WebClient phù hợp có thể gắn token của user; tránh gửi nhầm token tới endpoint ngoài audience/authorization policy.
- Tokens là secrets: lưu server-side an toàn, không đẩy refresh tokens vào browser hoặc logs nếu không cần.

Dùng đúng client registration và AS trust; khi nhiều OP/AS, chống mix-up và token substitution.

## 24. Migration danh tính CAS sang OIDC/OAuth: không ghép theo email

CAS principal thường là tên tài khoản do CAS phát, ví dụ `lan`. OIDC dùng `(iss,sub)`. OAuth access token cũng có `sub` nhưng subject semantics có thể phụ thuộc token type/grant.

**Không tự làm:**

~~~text
CAS principal = "lan"
OIDC email = "lan@example.test"
=> Đây chắc chắn cùng account (SAI)
~~~

**Đúng:** lập một bảng identity links có nguồn chứng cứ:

~~~text
local_account
  id = acct-57

external_identity
  (provider=corp-cas, subject=lan) -> acct-57
  (issuer=https://op.example.test, subject=oidc-u-901) -> acct-57
~~~

Hai links được nối bằng migration proof từ danh tính đã xác minh, workflow user link có MFA/step-up, hoặc dữ liệu mapping đáng tin do tổ chức quản trị. Không nối accounts của hai người khác nhau vì email trùng, email bị tái cấp hoặc username dùng lại.

**Với identity broker:** ứng dụng tin ID Token của **broker issuer** khi broker là OP trực tiếp. Đừng lấy `sub` của broker ghép với issuer upstream. Mapping CAS principal→OIDC subject phải có hợp đồng, audit và collision handling.

## 25. Quyền và tenant trong giai đoạn song song

Giả sử CAS phát group `finance-readers`, trong khi OAuth AS phát scope `invoice.read`. Không được tuyên bố hai chuỗi tự tương đương.

Một mẫu policy:

~~~text
ALLOW Billing.read(invoice)
  IF token/ticket valid for Billing
  AND authenticated subject mapped to active local account
  AND actor/client allowed to call Billing
  AND required protocol permission granted
  AND account is member of requested tenant
  AND invoice belongs to tenant
  AND domain rules allow viewing
ELSE DENY
~~~

Ở **CAS path**, “protocol permission” có thể là service/proxy policy và một role ánh xạ nội bộ. Ở **OAuth path**, có thể là scope `invoice.read` và token audience. Cả hai phải hội tụ tại **cùng domain authorization layer** để không xảy ra “CAS user được rộng hơn OAuth user” chỉ do khác filter chain.

**Vấn đề critical:** Token chỉ mang một tenant claim do AS phát chưa chứng minh người dùng hiện vẫn thuộc tenant đó sau khi quyền bị rút. Với operations nhạy cảm, kiểm membership hiện hành tại server hoặc dùng revocation/versioning phù hợp.

## 26. Ngăn credential confusion khi chạy song song CAS và OAuth

Trong giai đoạn chuyển tiếp, Billing có thể phải hỗ trợ cả CAS PT và OAuth access token. Cấu hình cần giữ **đường đi và validator riêng**:

~~~text
/api/legacy/cas/**  -> CAS PT filter + CAS proxyValidate
/api/v2/**          -> OAuth2 Bearer filter + JWT/introspection
            |
            v
    verified local principal / actor context
            |
            v
       Domain authorization
~~~

**Không:** viết một filter “nếu credential có prefix PT- thì CAS, còn lại thì thử parse JWT, nếu fail thì tin username claim”. Điều đó dễ dẫn tới credential confusion và bypass khi attacker cố tình chọn input.

**Thiết kế khuyến nghị:**

1. **SecurityFilterChain riêng**, `securityMatcher` không chồng lấn, thứ tự rõ.
2. CAS endpoints chỉ chấp nhận CAS PT theo đúng service URL/chain.
3. OAuth endpoints chỉ chấp nhận access token từ AS issuer/audience đã được tin.
4. Không fallback từ JWT invalid sang CAS guest login.
5. Tách credential storage, caches, audit tags và replay/revocation policy.
6. Mỗi đường đi tạo một **typed internal identity context** có protocol, issuer/provider, subject, client/actor, tenant và assurance.
7. Domain service chỉ nhận identity context đã verify và áp policy nhất quán.
8. Khi cutover hoàn tất, đóng hẳn legacy CAS path sau quan sát và kế hoạch rollback.

**Không thay đổi global filter chain mà không kiểm tra các URL khác** nếu một ứng dụng vừa có browser cookie login vừa có stateless APIs.

## 27. StatelessTicketCache và OAuth token caching không tương đương

Spring Security CAS có `StatelessTicketCache`: backend giữ **kết quả xác thực của một PT đã validate**, nên có thể dùng lại kết quả theo TTL cache.

OAuth2:

- JWT resource server thường verify access token mỗi request (hoặc tối ưu nội bộ tùy implementation); không “cấp lại nghĩa vụ CAS one-time”.
- Opaque token introspection có thể cache một response `active=true` theo policy, nhưng phải chịu rủi ro staleness.
- OAuth client có thể lưu **OAuth2AuthorizedClient** để tái sử dụng/refresh token theo lifecycle.
- **Refresh token** không phải CAS PGT; nó có issuance/revocation/reuse-detection rules khác.
- Không dùng cùng cache key/namespace cho CAS PT và OAuth access tokens, kể cả chúng có chuỗi giống nhau.

**Nếu migrate nhưng vẫn giữ cache PT lâu dài**, người dùng đã revoke ở AS/CAS có thể vẫn được Billing xác thực theo cache cũ. Trước cutover cần xác định revocation SLA và cách flush entries.

## 28. Java 17 độc lập: chọn đúng mô hình ủy nhiệm và kiểm phạm vi

Ví dụ JDK 17+ dưới đây mô phỏng policy tại Billing với hai đường xác thực. Nó **không xử lý CAS tickets hay OAuth JWT thật**, mà nhận input **đã giả định được validator đáng tin xác minh**. Chương trình giúp nhận diện lỗi: CAS PT dùng cho OAuth endpoint, M2M token giả user, sai audience, sai quyền, sai tenant và token delegation thiếu actor.

Tạo file **CasOAuthDecisionDemo.java**:

~~~java
import java.util.Set;

public class CasOAuthDecisionDemo {

    enum Kind { CAS_PROXY, OAUTH_USER, OAUTH_CLIENT, OAUTH_EXCHANGED }

    record Evidence(
            Kind kind,
            String audience,
            Set<String> rights,
            String user,
            String actor,
            String tenant,
            boolean verified) {}

    record Request(
            String audience,
            String requiredRight,
            String tenant,
            boolean needsUser,
            boolean needsActor) {}

    static String decide(Evidence e, Request r) {
        if (!e.verified()) {
            return "DENY_UNVERIFIED";
        }

        boolean casEndpoint = r.audience().startsWith("cas:");
        if (casEndpoint != (e.kind() == Kind.CAS_PROXY)) {
            return "DENY_PROTOCOL";
        }
        if (!r.audience().equals(e.audience())) {
            return "DENY_AUDIENCE";
        }
        if (!r.tenant().equals(e.tenant())) {
            return "DENY_TENANT";
        }
        if (!e.rights().contains(r.requiredRight())) {
            return "DENY_RIGHT";
        }
        if (r.needsUser() && e.user() == null) {
            return "DENY_USER_CONTEXT";
        }
        if (r.needsActor() && e.actor() == null) {
            return "DENY_ACTOR_CONTEXT";
        }
        return "ALLOW";
    }

    public static void main(String[] args) {
        Request legacy = new Request(
                "cas:billing", "invoice.read", "north", true, true);
        Request oauth = new Request(
                "oauth:billing", "invoice.read", "north", true, true);

        Evidence cas = new Evidence(
                Kind.CAS_PROXY, "cas:billing",
                Set.of("invoice.read"), "lan", "portal-a", "north", true);
        Evidence m2m = new Evidence(
                Kind.OAUTH_CLIENT, "oauth:billing",
                Set.of("invoice.read"), null, "portal-a", "north", true);
        Evidence delegated = new Evidence(
                Kind.OAUTH_EXCHANGED, "oauth:billing",
                Set.of("invoice.read"), "lan", "portal-a", "north", true);
        Evidence noActor = new Evidence(
                Kind.OAUTH_USER, "oauth:billing",
                Set.of("invoice.read"), "lan", null, "north", true);
        Evidence wrongAudience = new Evidence(
                Kind.OAUTH_EXCHANGED, "oauth:admin",
                Set.of("invoice.read"), "lan", "portal-a", "north", true);
        Evidence wrongScope = new Evidence(
                Kind.OAUTH_EXCHANGED, "oauth:billing",
                Set.of("invoice.write"), "lan", "portal-a", "north", true);
        Evidence wrongTenant = new Evidence(
                Kind.OAUTH_EXCHANGED, "oauth:billing",
                Set.of("invoice.read"), "lan", "portal-a", "south", true);
        Evidence notVerified = new Evidence(
                Kind.OAUTH_EXCHANGED, "oauth:billing",
                Set.of("invoice.read"), "lan", "portal-a", "north", false);

        System.out.println("CAS legacy: " + decide(cas, legacy));
        System.out.println("CAS as OAuth: " + decide(cas, oauth));
        System.out.println("M2M as user: " + decide(m2m, oauth));
        System.out.println("Exchanged token: " + decide(delegated, oauth));
        System.out.println("Missing actor: " + decide(noActor, oauth));
        System.out.println("Wrong audience: " + decide(wrongAudience, oauth));
        System.out.println("Wrong scope: " + decide(wrongScope, oauth));
        System.out.println("Wrong tenant: " + decide(wrongTenant, oauth));
        System.out.println("Invalid evidence: " + decide(notVerified, oauth));
    }
}
~~~

Chạy:

~~~bash
javac CasOAuthDecisionDemo.java
java CasOAuthDecisionDemo
~~~

**Stdout chính xác:**

~~~text
CAS legacy: ALLOW
CAS as OAuth: DENY_PROTOCOL
M2M as user: DENY_USER_CONTEXT
Exchanged token: ALLOW
Missing actor: DENY_ACTOR_CONTEXT
Wrong audience: DENY_AUDIENCE
Wrong scope: DENY_RIGHT
Wrong tenant: DENY_TENANT
Invalid evidence: DENY_UNVERIFIED
~~~

**Diễn giải:** CAS PT chỉ dùng trong trust boundary CAS; M2M token không có user context; token exchange có thể mang user và actor; sai audience/scope/tenant hoặc bằng chứng chưa kiểm đều bị từ chối.

**Giới hạn:** `Evidence.verified=true` là **giả định để học**, không phải validation thực. Trong production phải dùng CAS TicketValidator, OAuth JWT decoder/introspector, client authentication, replay protection, policy account/tenant và proper token exchange. `rights` của CAS trong demo là **quyền nội bộ đã được ứng dụng cho phép**, **không phải CAS OAuth scopes**. Không dùng lớp demo làm security filter hoặc Authorization Server.

## 29. Kế hoạch migration theo từng giai đoạn

### Pha 0 — Khảo sát và đặt tiêu chí

1. Inventory CAS Server, client versions, service registry, PGT/PT consumers, pgtUrl callbacks và proxy chains.
2. Liệt kê APIs, endpoints, user/machine identities, tenants và current authorization sources.
3. Xác định service nào thực sự cần **user delegation**, service nào chỉ cần M2M.
4. Đo baseline: CAS validation latency, ticket issue rate, proxy failures, login/logout, active sessions.
5. Chọn OAuth AS/OP đã được quản trị, khả năng token exchange/OPAQUE/JWT/PKCE.
6. Định nghĩa token audiences, scopes, user/actor claims, tenant representation và domain policy.
7. Xác định yêu cầu thu hồi, retention, compliance và khả năng rollback.

### Pha 1 — Chuẩn bị trust và identity mapping

1. Đăng ký OAuth clients và Resource Servers.
2. Thiết lập issuer/JWKS/introspection trust, signing key rotation và TLS.
3. Tạo identity links CAS principal ↔ local account ↔ OIDC issuer+sub khi cần.
4. Không auto-link chỉ bởi email trùng.
5. Định nghĩa AS policy cấp scope như **giao của quyền user + actor + audience + tenant**.
6. Chọn cách chuyển đổi: client_credentials, OIDC login, token exchange hoặc bridge.
7. Chốt người chịu trách nhiệm CAS session revocation và OAuth token revocation riêng.

### Pha 2 — Xây đường đi OAuth song song

1. Thêm `/api/v2/**` hoặc tuyến mới có OAuth Resource Server validator.
2. Giữ CAS proxy `/api/legacy/**` không đổi và giới hạn rõ.
3. Triển khai OAuth Client hoặc trusted bridge, chạy validator end-to-end.
4. Kiểm aud/scope/client actor/tenant/object cùng chính sách nghiệp vụ.
5. Redact CAS tickets và OAuth tokens khỏi logs.
6. Viết integration tests và security tests hai đường đi.
7. Đặt metrics theo protocol/outcome để phát hiện quyền sai hoặc tỉ lệ lỗi tăng.

### Pha 3 — Canary và tăng traffic

1. Chọn một tenant/service ít rủi ro và user/test accounts đã xác minh.
2. Chạy **shadow authorization decision** không tự động phát lệnh thanh toán hai lần.
3. So sánh quyết định CAS vs OAuth ở cùng nghiệp vụ; điều tra mọi mismatch quyền.
4. Thử JWT/opaque token expiry, CAS ticket replay, PGT rotation và OIDC session.
5. Thử outage AS, CAS, JWKS, Redis/cache, reverse proxy.
6. Tăng traffic theo các tiêu chí success/latency/security đã thống nhất.
7. Có nút rollback routing rõ, không mở tạm chấp nhận mọi token.

### Pha 4 — Cutover

1. Chuyển routing theo feature flags hoặc gateway rules có kiểm soát.
2. Không cho legacy CAS PT tự động gọi new OAuth-only endpoint.
3. Theo dõi 401 vs 403, audience mismatch, failed exchange và tenant denials.
4. Đánh giá active sessions và cached CAS Authentication còn sống.
5. Đặt mốc ngừng phát PGT/PT cho APIs đã chuyển.
6. Hạn chế hoặc xóa CAS filter/routes cũ theo kế hoạch, sau khi thật sự hết clients.

### Pha 5 — Retire và bảo trì

1. Xác minh toàn bộ consumers đã đổi, xử lý clients còn sót.
2. Thu hồi CAS PGT credentials, service registrations không còn cần và cache PT cũ.
3. Kiểm AS key lifecycle, token revocation và client secret rotation.
4. Lưu audit migration identity links/scopes và security approvals.
5. Cập nhật runbook/SLO/SLA và cảnh báo theo kiến trúc mới.
6. Chỉ retire CAS login nếu **không còn** ứng dụng khác phụ thuộc; chuyển một Billing API không đồng nghĩa có thể tắt toàn CAS Server.

## 30. Ma trận kiểm thử chuyển đổi

| Case | Tình huống | Kết quả bắt buộc |
| --- | --- | --- |
| 01 | CAS PT hợp lệ đến CAS endpoint | CAS validation đúng service/proxy chain |
| 02 | PT dùng tại OAuth-only endpoint | Từ chối, không fallback |
| 03 | OAuth token dùng tại CAS-only endpoint | Từ chối, không parse như PT |
| 04 | CAS PT cho Billing gửi sang Payroll | Từ chối wrong service |
| 05 | CAS PT replay sau CAS validate | Theo one-time/cached auth policy rõ |
| 06 | CAS proxy chain chứa proxy không được phép | CAS/backend từ chối |
| 07 | PGT đã bị thu hồi nhưng bridge vẫn nhận | Bridge phải fail closed |
| 08 | OAuth JWT sai chữ ký | 401 |
| 09 | JWT đúng chữ ký nhưng sai issuer | 401 |
| 10 | JWT đúng chữ ký nhưng sai audience | 401 |
| 11 | JWT hết hạn/nbf chưa hợp lệ | 401 |
| 12 | Access Token của AS khác gửi vào Billing | Từ chối mix-up |
| 13 | ID Token gửi tới Billing như Access Token | Từ chối token type/audience |
| 14 | Access token đúng aud nhưng thiếu scope | 403 |
| 15 | user token bị dùng như M2M client token | Không vượt client policy |
| 16 | M2M client_credentials giả user delegation | Không được xem là Lan |
| 17 | RFC 8693 token exchange không được AS hỗ trợ | Từ chối có kiểm soát, không tự mint token |
| 18 | Token exchange subject_token giả | AS phải từ chối |
| 19 | Token exchange actor trái policy | AS từ chối hoặc cấp quyền hẹp hợp lệ |
| 20 | Bridge không validate CAS PT | Không được cấp OAuth token |
| 21 | Bridge CAS PT sai service | Không cấp token |
| 22 | CAS→OIDC identity link thiếu chứng cứ | Không auto-link theo email |
| 23 | Client chỉ được invoice.read yêu cầu invoice.write | AS/RS từ chối escalation |
| 24 | User thuộc tenant north, request south | Domain policy từ chối |
| 25 | User đã bị disable sau token issue | Revocation/freshness policy được thực thi |
| 26 | JWT bị revoke khi còn thời hạn | Theo denylist/version/introspection SLA |
| 27 | Opaque token introspection active=false | 401 |
| 28 | Introspection outage | Fail closed khi không có evidence hợp lệ |
| 29 | CAS logout, OAuth token còn sống | Hành vi được định nghĩa; không hứa tự revoke |
| 30 | OAuth logout, CAS TGT còn sống | Có policy rõ, tránh thông báo global logout sai |
| 31 | Hai filter chains chồng lấn URL | Test phát hiện và sửa matcher/order |
| 32 | Gateway giả Host/X-Forwarded headers | Không thay đổi trusted service URL/issuer |
| 33 | Token exchange hai hops | Audit actor chain không bị mất nếu policy yêu cầu |
| 34 | Shadow traffic có write requests | Không thực thi business mutation hai lần |
| 35 | Quay lại legacy route theo rollback | Không dùng credential/cache trái trust boundary |
| 36 | Retire CAS service | Không còn active clients/tickets phụ thuộc |

Một bài kiểm thử chỉ nhìn thấy **HTTP 200** không đủ. Phải chứng minh **đúng identity, actor, audience, permission, tenant, object và revocation**. Phân biệt 401 (không được xác thực) với 403 (đã xác thực nhưng thiếu quyền).

## 31. Sai lầm thường gặp khi “đổi từ CAS sang OAuth2”

| Sai lầm | Rủi ro | Cách đúng |
| --- | --- | --- |
| Đặt PT vào `Authorization: Bearer` và gọi đó là OAuth | Resource Server không có AS/token contract | Token mới phải do AS phát, validator đúng giao thức |
| Dùng CAS username làm JWT `sub` do app tự ký | Impersonation và mất trust boundary | Mapping có proof, AS/broker đáng tin |
| Dùng client_credentials cho mọi request thay user | Mất user context/audit | OIDC user grant hoặc token exchange hợp lệ |
| Gán group CAS thành scope bằng string replace | Quyền vượt mức, tenant collision | Policy allowlist và domain authorization |
| Cho Billing nhận mọi JWT có chữ ký hợp lệ | Cross-audience/token confusion | Kiểm issuer, aud, token type, expiry, key trust |
| Dùng ID Token làm API Access Token | Sai mục đích token | Chỉ nhận access token dành cho Billing |
| Dùng JWT quá dài hạn và không revoke | Quyền bị rút vẫn tồn tại | TTL ngắn/introspection/denylist/epoch theo SLA |
| Cho CAS cached Authentication sống lâu khi cutover | Quyền cũ tồn tại song song | Evict cache/revocation policy |
| Không tách actor/subject | Che danh tính service đang thao tác | Token exchange/`act`, client auth và audit |
| Đổi sub/issuer nhưng ghép theo email | Account takeover | Dual identity link đã được xác minh |
| Token Exchange không có ở AS nhưng vẫn cố triển khai | Grant unsupported và workaround không an toàn | Kiểm tính năng AS hoặc dùng broker/flow khác |
| Không kiểm scope ở RS | Token có audience đúng nhưng quyền quá rộng | Scope + domain/tenant checks |
| Dùng redirect URI động từ browser | Open redirect/token leakage | Exact pre-registered redirects, PKCE/state |
| Mở proxy chain `acceptAnyProxy` trong giai đoạn migration | Trust quá rộng | Allowed proxies và strict target |
| Tắt CSRF toàn ứng dụng vì API dùng Bearer | Browser cookie flows bị yếu | Tách SecurityFilterChain và policy |
| “SAML/OIDC/CAS đều SSO” nên dùng chung validator | Confused deputy/cross-protocol injection | Validator riêng, normalized trusted identity context |

**Kết luận:** Đổi công nghệ không được làm mất các bảo đảm đang có về **CAS service restriction, proxy-chain restriction và local entitlement checks**. OAuth2 chỉ cải thiện kiến trúc khi các ranh giới đó được biểu diễn rõ và kiểm chứng end-to-end.

## 32. Sự cố trong migration: runbook xử lý

### A. Billing trả 401 khi Portal chuyển từ CAS PT sang OAuth token

1. Xác minh Portal đang gọi endpoint OAuth-only hay CAS legacy.
2. Đọc status của token issuance, không log raw token.
3. Kiểm issuer/audience/key/expiry của JWT hoặc introspection active của opaque token.
4. Kiểm OAuth client được AS cho phép grant hiện tại không.
5. Nếu Token Exchange, xem subject_token/actor_token có đúng type và được AS trust không.
6. Không fallback chấp nhận CAS PT trên endpoint mới chỉ để tránh lỗi.
7. Nếu rollback, dùng routing đã phê duyệt quay về endpoint CAS với ticket mới, không dùng credential sai protocol.

### B. OAuth token hợp lệ nhưng Billing trả 403

1. Kiểm scope `invoice.read` hoặc `invoice.write`.
2. Kiểm actor/client được quyền gọi Billing thay user chưa.
3. Kiểm local account link và tenant membership, object ownership.
4. Kiểm case/format role mapping và dữ liệu stale.
5. Không thêm `ROLE_ADMIN` như giải pháp tạm.
6. Phân biệt authorization mismatch do migration và token validation error.

### C. User đã logout CAS nhưng OAuth token vẫn gọi API được

1. Kiểm đây có phải JWT còn `exp` hay opaque active token.
2. Xác nhận có cơ chế truyền sự kiện CAS logout tới AS/token revocation không.
3. Nếu không, thừa nhận **hai lifecycle độc lập**.
4. Thu hồi refresh tokens/access tokens qua AS capability hoặc áp account/session epoch.
5. Test resource server cache/TTL và các APIs đã nhận token.
6. Sửa thông điệp UX nếu không thể bảo đảm global logout.

### D. CAS Proxy ngừng hoạt động khi thêm cầu nối

1. Kiểm PGT/pgtUrl certificate, CAS service registry và targetService của bridge.
2. Kiểm TicketValidator/allowed proxy chain đúng backend/bridge.
3. Kiểm PT one-time đã bị consume ở nơi khác hay chưa.
4. Kiểm bridge không retry PT cũ trong vòng lặp.
5. Kiểm AS có cho phép client bridge và đúng token exchange/issuance policy.
6. Nếu một mắt xích fail, không tự phát OAuth token bằng cách tin một CAS username raw.

### E. Quyền vượt tenant hoặc bị cấp rộng hơn trước

1. Ngừng canary hoặc rollback ngay theo incident severity.
2. Vô hiệu token/sessions đã phát sai qua revocation/expiry policy.
3. So CAS principal+proxy chain, OAuth subject+actor, local account và tenant.
4. Kiểm scope mapping, request tenant và resource ownership.
5. Điều tra cross-tenant exposure, audit affected objects và thông báo theo nghĩa vụ.
6. Chỉ tiếp tục rollout sau khi security owner duyệt fixes và regression tests.

## 33. Các câu hỏi tự đánh giá

**1. CAS Proxy có phải OAuth2 authorization grant không?**  
Không. CAS Proxy ủy nhiệm authentication qua PGT/PT và proxy chain, còn OAuth2 mô hình hóa authorization/access token do AS cấp.

**2. PT và OAuth Access Token có tương đương về vòng đời?**  
Không. PT theo CAS one-time validation; OAuth access token thường được dùng nhiều lần tới đúng audience trong lifetime. Spring cache PT chỉ tái dùng Authentication ở service.

**3. Một ứng dụng A gọi B không có user nên chọn gì?**  
Thường chọn `client_credentials`, với client identity và scopes dành cho B; không dùng một CAS user giả.

**4. Portal có user và muốn gọi Billing thay user nên làm gì?**  
Dùng token user-delegated có audience Billing, nếu cần actor lineage thì xem xét RFC 8693 Token Exchange khi AS hỗ trợ, hoặc trusted bridge được kiểm soát khi còn CAS.

**5. Có thể đổi CAS PT thành access token bằng cách Base64 decode hoặc đặt prefix Bearer không?**  
Không. Access token mới cần do AS tin cậy cấp theo grant và policy.

**6. OAuth2 Access Token luôn là JWT có `sub` người dùng phải không?**  
Không. Có opaque token; `sub` có thể là client trong client_credentials và semantics phụ thuộc profile/AS.

**7. Khi AS cấp `scope=invoice.read`, Billing đã được bỏ kiểm tenant chưa?**  
Chưa. Scope và audience không thay thế domain authorization.

**8. OIDC có tác dụng gì trong chuyển đổi?**  
OIDC hỗ trợ authentication cho RP với ID Token và `(iss,sub)`, thích hợp cho web login/federation; ID Token không phải API Access Token.

**9. Token Exchange có tự làm output token bị revoke khi input token bị thu hồi không?**  
Không mặc định. RFC 8693 nói đây không phải sự ràng buộc lifecycle tự động; triển khai phải xử lý revocation riêng.

**10. Có thể giữ CAS login và chuyển Billing API sang OAuth trước không?**  
Có, với AS/bridge/trust mapping phù hợp, validator paths tách biệt và kế hoạch chuyển đổi từng bước.

**11. Vì sao cần kiểm proxy chain khi nhận PT?**  
Vì PT được chuyển qua acting services; Billing chỉ nên tin những proxies được phê duyệt.

**12. Tại sao không nên dùng client_credentials để “đại diện cho Lan”?**  
Vì nó chứng minh danh tính/quyền của client, không mang user-delegated authorization theo mặc định.

**13. JWT local verification có giúp thu hồi quyền tức thì không?**  
Không mặc định. Cần TTL ngắn, introspection/denylist/version checks hoặc chính sách phù hợp.

**14. CAS logout có tự đăng xuất OAuth app và thu hồi mọi token không?**  
Không. Hai hệ có session/token lifecycle riêng; muốn đồng bộ phải có tích hợp.

**15. Trong giai đoạn chạy song song, điều gì quan trọng nhất?**  
Tách trust boundaries, kiểm đúng protocol/audience/actor/tenant và giữ domain authorization nhất quán, cùng khả năng rollback an toàn.

## 34. Checklist production trước cutover

- [ ] Hiểu CAS PGT/PT/ST, one-time validation, targetService, pgtUrl và proxy chain.
- [ ] Phân biệt rõ **proxy authentication** với **OAuth delegated authorization**.
- [ ] Inventory được các CAS consumers, service registries và proxy chains còn hoạt động.
- [ ] Có AS/OP được tin, không tự mint JWT từ username CAS chưa xác minh.
- [ ] Chọn đúng flow theo mục đích: OIDC Authorization Code + PKCE, client_credentials hoặc RFC 8693 khi hỗ trợ.
- [ ] Token Exchange được AS hỗ trợ chính thức; không giả định CAS PT là subject_token chuẩn.
- [ ] Bridge nếu có validate CAS PT đúng service/allowed proxy chain, xác thực actor/client và dùng AS issuance policy.
- [ ] Mapping identity CAS ↔ local account ↔ OIDC được kiểm chứng, không tự ghép email.
- [ ] Định nghĩa OAuth audiences/resources, scopes, client IDs và token types cho từng API.
- [ ] Billing Resource Server kiểm issuer, signature/introspection, audience, expiry và token type.
- [ ] Scope không thay domain authorization: tenant membership, object ownership và account status.
- [ ] Khi cần delegated actor, subject/actor semantics và `act` claim có contract end-to-end.
- [ ] Không dùng client_credentials thay user delegation.
- [ ] JWT/opaque token lifecycle, refresh/revoke/introspection/cache và SLA rõ.
- [ ] CAS logout/TGT/PGT revocation không bị nhầm với OAuth token revocation.
- [ ] Legacy CAS filter và OAuth Bearer filter tách endpoints/matchers, không fallback khi validation fail.
- [ ] CSRF/login, PKCE/state/nonce, redirect URIs, mTLS/TLS và trusted proxy headers được kiểm tra.
- [ ] Không log PT/PGT, access/refresh tokens, raw assertions hoặc client secrets.
- [ ] Có test đúng/sai service, aud, scope, actor, tenant, expired/revoked, cross-protocol confusion.
- [ ] Có canary/shadow authz, rollout metrics, security approvals và quy trình rollback.
- [ ] Không retire CAS Server nếu còn client phụ thuộc, không tự mở trust để vượt qua lỗi migration.

## 35. Kết luận

**CAS Proxy không phải phiên bản cũ của OAuth2 Access Token.** CAS Proxy dùng PGT/PT và proxy chain để mang ngữ cảnh xác thực qua các CAS services; OAuth2 dùng AS, grants, access tokens, scopes và audiences để cấp quyền truy cập resources. Khi có người dùng, cần phân biệt **subject** và **acting client**; khi không có người dùng, `client_credentials` có thể phù hợp. **OIDC** giải quyết authentication/login cho clients mới; **RFC 8693 Token Exchange** là một hướng thể hiện delegated actor khi AS hỗ trợ.

**Không có lựa chọn chung cho mọi dự án.** Có thể **giữ CAS** nếu legacy ổn định và phạm vi hẹp; **chuyển M2M sang client_credentials**; **dùng OIDC Authorization Code + PKCE** cho web login mới; **dùng Token Exchange** cho user on-behalf-of; hoặc **dùng trusted CAS→OAuth bridge** để chuyển các APIs từng bước. Phương án nào cũng phải giữ hoặc tăng mức bảo đảm: **đúng issuer/CAS trust, đúng target/audience, đúng user+actor, quyền tối thiểu, tenant isolation, revocation và audit**.

### Tài liệu tham khảo chính thức

- Apereo CAS — CAS Protocol Specification: proxy callback, `/proxy`, `/proxyValidate`, PGT/PT và chuỗi proxies: https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- Spring Security — CAS Authentication và Proxy Ticket Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- IETF RFC 6749 — The OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- IETF RFC 9700 (January 2025) — Best Current Practice for OAuth 2.0 Security, PKCE, mix-up và token security: https://www.rfc-editor.org/rfc/rfc9700
- IETF RFC 8693 — OAuth 2.0 Token Exchange, `subject_token`, `actor_token` và `act`: https://www.rfc-editor.org/rfc/rfc8693
- IETF RFC 8707 — Resource Indicators for OAuth 2.0: https://www.rfc-editor.org/rfc/rfc8707
- IETF RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- IETF RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- IETF RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- IETF RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP): https://www.rfc-editor.org/rfc/rfc9449
- OpenID Connect Core — ID Token và Authentication Code Flow: https://openid.net/specs/openid-connect-core-1_0.html
- Spring Security — OAuth2 Client Authorized Clients and token use: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — OAuth2 Resource Server JWT `issuer-uri` và `audiences`: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Resource Server Opaque Token introspection: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html

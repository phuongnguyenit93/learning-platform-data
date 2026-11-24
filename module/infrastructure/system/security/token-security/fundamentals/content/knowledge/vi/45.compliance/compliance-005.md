# Privacy của subject identifier

> **Chương:** Compliance  
> **Phạm vi:** Bảo vệ định danh chủ thể trong JWT, opaque access token và luồng OAuth 2.0/OpenID Connect; giảm khả năng nhận diện, liên kết hoạt động và rò rỉ dữ liệu qua token.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích claim `sub` biểu diễn chủ thể nào và vì sao subject identifier có thể là dữ liệu cá nhân dù không chứa tên thật.
2. Phân biệt public subject identifier, pairwise subject identifier, định danh nội bộ và mã phiên/token.
3. Chọn định danh tối thiểu cần đưa vào access token hoặc ID token theo audience và mục đích xử lý.
4. Hạn chế việc subject identifier xuất hiện trong log, metric, trace, URL, cache, event và hệ thống phân tích.
5. Thiết kế kiểm thử chứng minh các client không thể liên kết người dùng ngoài phạm vi được phép và dữ liệu định danh được bảo vệ trong toàn bộ vòng đời token.

## 1. Subject identifier là gì?

Trong OpenID Connect (OIDC), claim `sub` (subject) là định danh của người dùng/chủ thể mà issuer xác thực. Nó giúp client hoặc resource server liên kết một token với một chủ thể cụ thể. Ví dụ:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "usr-pairwise-7f31a9",
  "aud": "orders-web",
  "exp": 1900000900
}
~~~

Giá trị `sub` không nhất thiết là tên, email hay số điện thoại. Nó thường là một chuỗi định danh do Identity Provider (IdP) tạo. Tuy nhiên, **một định danh không chứa tên vẫn có thể là dữ liệu cá nhân** nếu nó cho phép nhận diện trực tiếp hoặc liên kết các hoạt động của cùng một người.

Ví dụ, một chuỗi ngẫu nhiên `usr-7f31a9` có thể không tiết lộ danh tính khi nhìn riêng lẻ. Nhưng nếu hệ thống có bảng ánh xạ từ chuỗi đó tới tài khoản Alice, hoặc nhiều dịch vụ dùng cùng chuỗi để ghép lịch sử giao dịch, nó vẫn có thể nhận diện hay theo dõi một cá nhân.

Cần phân biệt các khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Subject identifier | Định danh chủ thể trong miền của issuer | OIDC claim `sub` |
| Username/display name | Tên đăng nhập hoặc tên hiển thị | `alice@example.com`, `Alice Nguyen` |
| Internal user ID | Khóa nội bộ trong hệ thống nghiệp vụ | UUID trong bảng users |
| Tenant ID | Miền dữ liệu/khách hàng mà chủ thể đang hoạt động | UUID của tổ chức |
| Session ID | Định danh phiên đăng nhập | Session handle ngẫu nhiên |
| Token ID (`jti`) | Định danh một JWT cụ thể khi issuer phát hành claim này | ID dùng cho audit/revocation |
| Client ID | Định danh ứng dụng OAuth/OIDC | `orders-web` |

Các giá trị trên phục vụ mục đích khác nhau. Không dùng `sub` thay cho `jti`, session ID hay tenant ID. Cũng không mặc định rằng client ID hoặc tenant ID là vô danh; khi kết hợp với dữ liệu khác, chúng có thể tiết lộ tổ chức hoặc hành vi sử dụng.

### Vì sao subject identifier có rủi ro riêng tư?

- **Nhận diện:** bảng ánh xạ hoặc dữ liệu phụ có thể biến mã định danh thành danh tính thật.
- **Liên kết (linkability):** cùng một `sub` xuất hiện ở nhiều client, API hoặc log cho phép ghép hoạt động của người dùng.
- **Theo dõi dài hạn:** định danh ổn định giúp xây dựng lịch sử hành vi qua nhiều phiên.
- **Rò rỉ gián tiếp:** subject ID có thể xuất hiện trong URL, log, trace, analytics, export hoặc thông báo lỗi.
- **Mở rộng phạm vi:** một service nhận token có thể lưu subject ID lâu hơn mục đích ban đầu hoặc chia sẻ sang bên thứ ba.

Bảo vệ subject identifier vì vậy là một phần của data minimization, privacy by design và kiểm soát vòng đời token.

## 2. Public và pairwise subject identifier trong OIDC

OIDC Core định nghĩa hai loại subject identifier chính:

### Public subject identifier

Issuer dùng cùng một `sub` cho một người dùng trên các client/Relying Party (RP) thuộc phạm vi phát hành của issuer.

Ưu điểm là dễ liên kết tài khoản giữa các ứng dụng khi có mục đích và sự đồng ý phù hợp. Nhược điểm là các RP có thể so sánh `sub` để nhận ra cùng một người, kể cả khi họ không nên chia sẻ dữ liệu với nhau.

### Pairwise subject identifier

Issuer tạo một `sub` khác nhau cho cùng một người dùng ở các sector/client khác nhau. Nhờ đó, RP thuộc các sector khác nhau không thể chỉ dựa vào `sub` để biết hai tài khoản có phải cùng một người hay không.

Ví dụ:

| Người dùng nội bộ | RP/sector | Subject identifier được cấp |
| --- | --- | --- |
| Alice | Orders Web | `pairwise-a81f` |
| Alice | Support Portal | `pairwise-20bd` |
| Alice | Analytics Partner | `pairwise-c91a` |
| Bob | Orders Web | `pairwise-f482` |

IdP vẫn có thể biết các giá trị trên cùng ánh xạ về Alice. Pairwise identifier giảm khả năng các RP tự liên kết tài khoản; nó **không làm cho dữ liệu trở thành anonymous** và không ngăn được mọi hình thức fingerprinting.

~~~mermaid
flowchart TD
    U["Tài khoản Alice tại IdP"] --> M["Bộ ánh xạ subject nội bộ"]
    M --> A["Orders sector: pairwise-a81f"]
    M --> B["Support sector: pairwise-20bd"]
    M --> C["Partner sector: pairwise-c91a"]
    A --> R1["Orders Web RP"]
    B --> R2["Support Portal RP"]
    C --> R3["Analytics Partner RP"]
    R1 -. "Không tự suy ra cùng người dùng" .- R2
    R2 -. "Không tự suy ra cùng người dùng" .- R3
~~~

### Sector identifier

Pairwise subject thường được tính theo một **sector identifier** do OIDC provider xác định. Các client có thể được gom trong cùng một sector theo quy tắc của provider; các client khác sector sẽ nhận subject khác nhau.

Do đó, pairwise không nhất thiết có nghĩa “mỗi client luôn một mã riêng”. Cần hiểu chính sách sector của IdP trước khi thiết kế account linking, migration hoặc báo cáo liên ứng dụng.

### Chọn loại subject nào?

| Nhu cầu | Hướng lựa chọn |
| --- | --- |
| Nhiều RP độc lập, không cần biết người dùng có mặt ở hệ thống khác | Pairwise |
| Các ứng dụng thuộc cùng một tổ chức cần liên kết tài khoản có kiểm soát | Cùng sector pairwise hoặc quy trình account linking riêng |
| Hệ thống phân tích của đối tác không cần định danh chung | Pairwise hoặc mã giả danh riêng theo mục đích |
| Dịch vụ nội bộ cần ánh xạ chủ thể nghiệp vụ | Dùng mapping server-side; chỉ truyền định danh cần thiết |
| Báo cáo tổng hợp không cần theo dõi từng người | Ưu tiên aggregate hoặc dữ liệu đã được ẩn danh phù hợp |

Không chọn public subject chỉ vì nó thuận tiện cho việc join dữ liệu. Hãy xác định mục đích, bên nhận, thời hạn lưu và cơ sở cho phép liên kết trước khi bật chia sẻ định danh.

## 3. Định danh trong access token và ID token

ID token và access token phục vụ hai đối tượng khác nhau:

- **ID token** được OIDC phát hành cho client để client xác nhận sự kiện xác thực và chủ thể đã đăng nhập. Claim `sub` có ý nghĩa trong phạm vi issuer.
- **Access token** được phát hành để client gọi resource server. Resource server chỉ nên nhận các claim cần thiết để thực thi quyền và xử lý request.
- **Refresh token** dùng để xin access token mới theo authorization server; đây là credential nhạy cảm, cần bảo vệ và quản lý vòng đời riêng. Không cần đưa toàn bộ hồ sơ người dùng vào refresh token.

Ví dụ payload access token tối thiểu:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "pairwise-a81f",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1900000900
}
~~~

Payload minh họa không chứa email, tên, số điện thoại hay địa chỉ. API có thể dùng cặp `(iss, sub)` để ánh xạ chủ thể sang hồ sơ nghiệp vụ khi thật sự cần. Trong OIDC, `sub` là định danh duy nhất trong phạm vi issuer; không giả định `sub` tự nó duy nhất trên toàn bộ hệ thống có nhiều issuer.

**JWT được ký không đồng nghĩa payload được mã hóa.** Với JWS thông thường, người cầm token có thể đọc header và payload. Chữ ký bảo vệ tính toàn vẹn, không che giấu claims. Vì vậy, không đưa dữ liệu nhạy cảm vào JWT với giả định người dùng không thể đọc nó. Nếu cần nội dung token được bảo mật ở tầng token, phải dùng cơ chế mã hóa phù hợp (JWE) và vẫn phải đánh giá bên nhận, key management và rủi ro lưu trữ.

Với opaque access token, resource server thường dùng introspection hoặc cơ chế nội bộ để lấy trạng thái/quyền. Opaque token không tự động giải quyết quyền riêng tư: token vẫn có thể là bearer credential, và introspection response/log/database có thể chứa subject identifier.

### Claim nào nên được phát hành?

Áp dụng nguyên tắc “mỗi claim phải có lý do”:

| Claim/thuộc tính | Câu hỏi trước khi phát hành |
| --- | --- |
| `sub` | Resource server có cần nhận diện chủ thể không? Có thể dùng pairwise hoặc mapping server-side không? |
| `iss` | Resource server cần xác minh issuer nào? |
| `aud` | Token chỉ dành cho API nào? |
| `scope` | API cần quyền thao tác cụ thể nào? Có đang cấp quá rộng không? |
| `tenant_id` | API có thực sự cần tenant context? Giá trị có được xác lập từ membership đáng tin không? |
| `email` / `name` | API có cần dữ liệu định danh trực tiếp hay chỉ cần một kết quả nghiệp vụ? |
| `jti` | Có yêu cầu audit, chống replay hoặc thu hồi theo token không? Lưu ở đâu, trong bao lâu? |
| `client_id` | Có cần để phân biệt ứng dụng gọi API không? Có thể dùng mã client đã chuẩn hóa không? |

Không đưa email hoặc số điện thoại vào `sub` để thuận tiện. Email có thể thay đổi, thường là dữ liệu cá nhân trực tiếp và có thể bị dùng để đăng nhập ở nhiều hệ thống. Subject identifier nên ổn định theo hợp đồng của issuer và không mang ý nghĩa nghiệp vụ dễ đoán.

Nếu API chỉ cần biết người dùng có quyền đọc đơn hàng trong tenant hiện tại, có thể chỉ cần `sub` giả danh, `aud`, `scope` và tenant context đã được xác minh. Tên hiển thị hoặc email nên được lấy từ profile service theo quyền riêng, khi chức năng thật sự cần.

## 4. Ánh xạ subject an toàn giữa IdP và hệ thống nghiệp vụ

Resource server thường cần liên kết token với hồ sơ người dùng nội bộ. Hãy sử dụng một bảng ánh xạ có quyền truy cập giới hạn:

~~~sql
CREATE TABLE external_subject_mapping (
    issuer_id       VARCHAR(80) NOT NULL,
    subject_value   VARCHAR(255) NOT NULL,
    internal_user_id UUID NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    PRIMARY KEY (issuer_id, subject_value)
);
~~~

Ví dụ này dùng issuer_id là mã issuer cấu hình nội bộ; không nhất thiết lưu URL issuer thô ở mọi bảng. Khóa ghép giúp tránh giả định hai issuer khác nhau không bao giờ cấp cùng chuỗi `sub`.

Các nguyên tắc thiết kế:

1. **Namespace theo issuer:** dùng `(iss, sub)` hoặc cặp issuer ID/subject làm khóa tra cứu; không dùng `sub` đơn lẻ trong hệ thống multi-issuer.
2. **Tách mapping khỏi hồ sơ:** bảng ánh xạ có thể chứa liên kết định danh trực tiếp tới internal user ID, nên cần quyền đọc/ghi chặt, audit và retention riêng.
3. **Không để lộ khóa nội bộ:** không phát hành primary key cơ sở dữ liệu nếu client/resource server không cần biết.
4. **Kiểm soát account linking:** chỉ liên kết hai subject sau khi chứng minh quyền kiểm soát cả hai tài khoản theo flow tin cậy; không join dựa trên email trùng đơn thuần.
5. **Xử lý thay đổi issuer/sector:** migration subject phải có quy trình xác thực và audit; không âm thầm gán mã mới vào tài khoản chỉ vì chuỗi định danh trông giống nhau.
6. **Giới hạn truy cập:** service nghiệp vụ chỉ nhận kết quả mapping hoặc định danh giả danh cần thiết; không cấp quyền đọc bảng ánh xạ cho mọi service.

### Ví dụ kiểm tra mapping

~~~java
record ExternalSubject(String issuerId, String subject) {}

Optional<UserId> resolveSubject(VerifiedJwt jwt) {
    String issuerId = trustedIssuerRegistry.requireId(jwt.getIssuer());
    String subject = requireNonBlank(jwt.getSubject());

    return subjectMappingRepository
            .findInternalUserId(issuerId, subject);
}
~~~

Đây là ví dụ minh họa: `VerifiedJwt` phải là token đã được decoder xác minh chữ ký, issuer, audience và thời hạn. Không truyền JWT chưa xác thực vào mapping repository. Kết quả mapping cũng không tự cấp quyền; ứng dụng vẫn phải kiểm tra membership, scope và quyền trên tài nguyên.

Nếu hệ thống không cần biết danh tính thật, tránh thực hiện mapping. Mỗi lần mở thêm đường mapping là thêm một nơi có thể liên kết hành vi với một cá nhân.

## 5. Giảm rò rỉ subject identifier trong log, metric và trace

Subject identifier thường rò rỉ ngoài ý muốn qua telemetry. Ví dụ, log `user=alice@example.com` hoặc metric có label `sub` khiến định danh được sao chép sang nhiều hệ thống quan sát, nơi có thể có quyền truy cập rộng hơn cơ sở dữ liệu nghiệp vụ.

### Log bảo mật có cấu trúc

Nên ghi các trường phục vụ điều tra mà không cần lưu subject thô:

~~~json
{
  "event": "access_token_validation_failed",
  "service": "orders-api",
  "issuer_id": "corporate-idp",
  "failure_class": "invalid_audience",
  "request_id": "req-8b21",
  "route": "/api/orders/{orderId}",
  "http_status": 401
}
~~~

Không ghi:

- Header `Authorization` hoặc chuỗi Bearer token.
- JWT đầy đủ, refresh token, cookie phiên hoặc secret.
- Email, số điện thoại, tên, địa chỉ hoặc toàn bộ payload claims khi không cần.
- Subject identifier thô nếu không có mục đích audit rõ ràng và quyền truy cập tương ứng.
- Private key, client secret, introspection credential hoặc dữ liệu xác thực JWKS.

Nếu điều tra yêu cầu liên kết các sự kiện của cùng một chủ thể, có thể tạo pseudonym phục vụ riêng cho mục đích đó bằng HMAC với secret được quản lý an toàn:

~~~text
audit_subject_ref = HMAC-SHA-256(
    audit_key,
    issuer_id || ":" || subject
)
~~~

HMAC giúp người không có secret khó tính ngược từ email hoặc subject có cấu trúc dễ đoán. Tuy nhiên, giá trị HMAC vẫn ổn định và có thể liên kết các sự kiện trong phạm vi sử dụng khóa đó; **đây vẫn là pseudonymous data**, không phải dữ liệu đã ẩn danh.

Dùng key riêng cho từng mục đích hoặc miền dữ liệu, kiểm soát ai có thể tạo/tra cứu giá trị, quản lý rotation và không tái sử dụng cùng một pseudonym cho analytics, support và security audit nếu không có lý do. Hash không khóa như SHA-256 trên email/ID dễ bị dò từ danh sách giá trị phổ biến, nên không thay thế HMAC.

### Metric và cardinality

Không đặt `sub`, `jti`, email, tenant ID tự do hoặc token làm label của Prometheus. Mỗi subject có thể tạo một time series mới, làm cardinality tăng không giới hạn và biến hệ thống metric thành nơi lưu định danh dài hạn.

Metric nên dùng nhãn có tập giá trị hữu hạn:

~~~text
token_validation_failures_total{
  service="orders-api",
  issuer_id="corporate-idp",
  stage="audience",
  outcome="failure"
}
~~~

Nếu cần số lượng người dùng bị ảnh hưởng, hãy tính bằng pipeline phân tích có quyền truy cập và retention riêng, hoặc dùng số liệu aggregate đã giảm khả năng nhận diện. Không biến dashboard vận hành thành danh sách người dùng.

### Trace, baggage và error reporting

- Không đưa subject, email hoặc token vào trace baggage mặc định.
- Không gắn claim vào span attribute nếu người vận hành không cần và chính sách không cho phép.
- Bộ lọc exception/APM phải che header Authorization và token trong request/response body.
- Tránh dùng subject identifier trong URL hoặc query string vì có thể xuất hiện trong browser history, reverse proxy log, referrer và hệ thống analytics.
- Khi cần liên kết một request, ưu tiên request ID/trace ID ngẫu nhiên; quyền tra cứu về chủ thể phải nằm ở hệ thống audit được bảo vệ.

## 6. Cache, event, queue và dữ liệu phân tích

Privacy của subject không kết thúc tại API gateway. Khi định danh được truyền sang các tầng khác, cần giới hạn mục đích và thời gian sử dụng.

| Thành phần | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Cache | Key chứa subject thô hoặc cache dùng chung giữa người dùng | Dùng key nội bộ giả danh, namespace theo issuer/tenant/quyền; TTL ngắn phù hợp |
| Queue/message | Event chứa email/sub cho consumer không cần | Chỉ gửi định danh tối thiểu hoặc reference có kiểm soát |
| Data warehouse | Ghép hành vi từ nhiều sản phẩm bằng cùng subject | Pairwise/pseudonym theo purpose, phân quyền dataset, retention |
| Search/index | Subject được index và truy vấn rộng | Không index nếu không cần; giới hạn field và access policy |
| Export/report | CSV chứa định danh vượt nhu cầu báo cáo | Aggregate, masking hoặc pseudonymize |
| Object storage | Đường dẫn file chứa subject/email | Dùng object key ngẫu nhiên, kiểm tra authorization trước khi cấp URL |
| Audit store | Log liên kết danh tính lưu quá lâu hoặc nhiều người đọc | Tách quyền, retention, audit truy cập và quy trình tra cứu |
| Backup | Mapping bị giữ sau khi xóa ở hệ thống chính | Đồng bộ retention/deletion với lịch backup và quy trình restore |

Cache key cần giữ đủ ngữ cảnh bảo mật để tránh trả dữ liệu giữa hai subject, issuer hoặc tenant khác nhau. Không vì mục tiêu riêng tư mà loại bỏ mọi phân biệt cần thiết để authorization. Pseudonym hóa key nhưng vẫn phải kiểm tra quyền trước khi trả dữ liệu.

Với event bất đồng bộ, consumer chỉ nhận định danh nếu cần cho nghiệp vụ. Nếu cần gọi ngược profile service, gửi một reference nội bộ có phạm vi và xác thực thay vì phát tán email hoặc access token gốc. Không nhúng bearer token vào message để “tiện” cho worker.

## 7. Vòng đời subject identifier và vòng đời token

Subject identifier có thể tồn tại lâu hơn access token. Một access token có thể hết hạn sau vài phút, nhưng log, cache, warehouse và mapping table vẫn giữ `sub` trong nhiều tháng. Vì vậy, quản lý riêng hai vòng đời:

### Khi phát hành token

- Chọn public/pairwise subject theo mô hình chia sẻ dữ liệu và sector của client.
- Chỉ phát hành claim cần thiết cho audience.
- Không đưa thông tin định danh trực tiếp vào payload nếu API không cần.
- Gắn scope, audience và tenant context theo quyền thực tế; không dùng subject ID để thay thế authorization.
- Xác định nơi lưu mapping, log và audit trước khi bật claim.

### Khi refresh hoặc cấp token mới

- Refresh token phải được bảo vệ như credential có thể cấp lại access token; lưu trữ an toàn, rotation và phát hiện reuse theo chính sách.
- Không cho phép client tự thay `sub` trong refresh request.
- Authorization server phải giữ liên kết session/client/subject và kiểm tra trạng thái tài khoản, membership, consent hoặc policy cần thiết trước khi cấp token mới.
- Token mới phải giữ đúng subject mapping hoặc áp dụng migration có kiểm soát nếu subject/issuer/sector thay đổi.

### Khi thu hồi hoặc xóa tài khoản

- Thu hồi session/refresh token và chặn việc cấp token mới theo chính sách.
- Đánh giá access token đang còn hiệu lực: TTL, introspection, denylist hoặc policy version có thể ảnh hưởng thời gian quyền bị thu hồi có hiệu lực.
- Xóa hoặc hạn chế mapping theo yêu cầu và nghĩa vụ lưu trữ áp dụng; xem xét log, cache, event, warehouse và backup.
- Giữ lại audit tối thiểu khi có cơ sở hợp lệ, với quyền truy cập và retention được xác định; không mặc định giữ toàn bộ subject vô thời hạn.
- Đảm bảo việc xóa/ẩn danh không phá vỡ tính toàn vẹn của dữ liệu cần lưu theo nghĩa vụ pháp lý hoặc tranh chấp.

### Thay đổi pairwise subject hoặc issuer

Khi client đổi sector, issuer migration hoặc IdP thay đổi thuật toán tạo subject, cùng một người dùng có thể nhận giá trị `sub` mới. Không tự động suy ra hai subject thuộc cùng một người nếu không có bằng chứng xác thực. Quy trình account linking/migration phải xác thực chủ thể, lưu audit và xử lý session/token cũ theo policy.

Một subject ID mới không tự động làm access token cũ vô hiệu. Cần thiết kế đồng bộ mapping, token expiry/revocation và cache invalidation.

## 8. Pseudonymization, anonymization và nghĩa vụ riêng tư

**Pseudonymization (giả danh hóa)** thay định danh trực tiếp bằng một mã khác, trong khi vẫn có thể liên kết lại thông qua thông tin bổ sung được giữ riêng. Ví dụ, thay email bằng pairwise `sub` hoặc HMAC subject reference.

**Anonymization (ẩn danh hóa)** đòi hỏi dữ liệu không còn cho phép nhận diện cá nhân theo tiêu chuẩn áp dụng, xét cả dữ liệu bổ sung và khả năng liên kết hợp lý. Chỉ thay email bằng một UUID hoặc hash không có nghĩa dữ liệu đã được ẩn danh.

Theo GDPR, dữ liệu giả danh hóa vẫn có thể là personal data khi có thể quy về một cá nhân bằng thông tin bổ sung; pseudonymization là biện pháp giảm rủi ro và hỗ trợ bảo vệ dữ liệu. Tổ chức cần đánh giá luật áp dụng, mục đích, cơ sở xử lý, thời hạn lưu, quyền của chủ thể dữ liệu và nghĩa vụ thông báo phù hợp. Bài học này giải thích nguyên tắc kỹ thuật, không thay thế tư vấn pháp lý cho một tình huống cụ thể.

### Privacy by design checklist

Trước khi phát hành hoặc chia sẻ subject identifier, hãy trả lời:

1. **Purpose:** service nhận identifier cần thực hiện nghiệp vụ cụ thể nào?
2. **Necessity:** có thể dùng aggregate, role/scope, boolean result hoặc reference ngắn hạn thay cho subject không?
3. **Audience:** những API/client nào thực sự cần biết chủ thể?
4. **Linkability:** các bên độc lập có thể ghép hoạt động qua cùng identifier không?
5. **Retention:** dữ liệu được giữ bao lâu, khi nào xóa hoặc rotate?
6. **Access:** ai có thể đọc mapping hoặc tra cứu pseudonym về danh tính thật?
7. **Security:** token, mapping, log và backup được mã hóa/bảo vệ thế nào?
8. **Rights and governance:** có quy trình xử lý yêu cầu truy cập, sửa, xóa, phản đối hoặc giới hạn xử lý khi luật áp dụng yêu cầu không?

Ghi quyết định vào data inventory hoặc privacy assessment phù hợp: loại identifier, mục đích, nguồn, bên nhận, retention, hệ thống lưu và chủ sở hữu kiểm soát.

## 9. Ví dụ thiết kế: Orders API không cần email

**Bối cảnh:** Người dùng đăng nhập qua OIDC, sau đó gọi Orders API. API cần biết chủ thể để kiểm tra quyền đọc đơn trong tenant đang hoạt động. API không gửi email và không hiển thị hồ sơ cá nhân.

Một thiết kế hợp lý:

1. IdP xác thực người dùng và cấp access token dành cho `orders-api`.
2. Token chứa `iss`, pairwise `sub`, `aud`, `exp`, scope phù hợp và tenant context đã được xác minh theo hợp đồng.
3. Resource server xác minh chữ ký, issuer, audience và thời gian; sau đó kiểm tra scope.
4. Service dùng `(issuer_id, sub)` để tìm internal user ID qua mapping có kiểm soát, nếu nghiệp vụ cần.
5. Repository lọc theo tenant đã xác thực và kiểm tra quyền trên từng order.
6. Audit event ghi request ID, issuer ID, action, resource reference và outcome; subject reference chỉ được thêm nếu policy audit yêu cầu.
7. Metric chỉ đếm outcome/stage theo service và issuer ID, không tạo series theo từng subject.

Ví dụ request:

~~~http
GET /api/orders/ord-102
Authorization: Bearer <access-token>
~~~

API không cần nhận `email` hoặc `name` để thực hiện thao tác. Nếu giao diện cần tên hiển thị, client có thể gọi profile endpoint riêng với scope/audience và quyền phù hợp. Không mở rộng access token của Orders API thành hồ sơ cá nhân chỉ để tránh một lần gọi API.

### Những quyết định cần ghi lại

| Quyết định | Thiết kế minh họa |
| --- | --- |
| Subject type | Pairwise cho RP độc lập |
| Mapping key | Cặp issuer ID + subject |
| Access token | Chỉ claim cần thiết cho orders API |
| Email/name | Không phát hành cho Orders API |
| Logs | Request ID, issuer ID, failure class, action |
| Metrics | Service, environment, issuer ID, outcome |
| Retention | Theo purpose và chính sách lưu trữ được phê duyệt |
| Account linking | Flow xác thực riêng, không join bằng email trùng |

## 10. Bộ ca kiểm thử privacy

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| PRIV-SUB-01 | Cùng người dùng đăng nhập hai RP thuộc hai sector khác nhau | Nhận pairwise subject khác nhau |
| PRIV-SUB-02 | Hai RP cùng sector theo cấu hình provider | Subject theo quy tắc sector đã công bố; không tự giả định khác nhau |
| PRIV-SUB-03 | Hai issuer cấp cùng chuỗi `sub` | Mapping không va chạm vì có issuer namespace |
| PRIV-SUB-04 | Access token của Orders API | Không chứa email/name nếu API không cần |
| PRIV-SUB-05 | JWT được ký nhưng payload có thể decode | Không có dữ liệu nhạy cảm dựa trên giả định payload được ẩn |
| PRIV-SUB-06 | Request xác thực thất bại | Log không chứa Authorization header/JWT |
| PRIV-SUB-07 | Metric được tạo cho nhiều subject ngẫu nhiên | Không tạo label theo `sub` hoặc token |
| PRIV-SUB-08 | Audit pseudonym dùng HMAC | Chỉ liên kết trong đúng purpose/key domain |
| PRIV-SUB-09 | Client cố gửi `sub` khác trong request | Server bỏ qua hoặc từ chối; subject lấy từ token đã xác thực |
| PRIV-SUB-10 | Client yêu cầu liên kết hai tài khoản chỉ vì email trùng | Không tự động liên kết |
| PRIV-SUB-11 | Refresh token bị reuse theo policy rotation | Session/refresh token được xử lý theo cơ chế phát hiện reuse; không đổi chủ thể tùy ý |
| PRIV-SUB-12 | Subject mapping bị xóa theo quy trình | Cache, downstream reference và retention liên quan được xử lý nhất quán |

Bên cạnh test tự động, nên rà soát mẫu log, trace, metric label, export và event schema. Kiểm thử bằng cách tìm email/subject/token giả lập trong các bản ghi đầu ra để xác nhận dữ liệu không bị phát tán.

## 11. Bài tập thực hành

**Tình huống:** Một công ty có hai sản phẩm độc lập: Orders và Support. Cả hai dùng chung IdP. Hệ thống hiện phát public subject identifier và ghi `sub` vào log, metric label và event analytics. Đội phân tích muốn ghép hành vi người dùng giữa hai sản phẩm.

1. Rủi ro privacy nào phát sinh từ public subject identifier?
2. Pairwise subject giúp giảm khả năng liên kết giữa Orders và Support như thế nào?
3. Nếu bộ phận analytics có mục đích hợp lệ cần thống kê người dùng duy nhất, hãy đề xuất cách xử lý dữ liệu có giới hạn và kiểm soát.
4. Vì sao hash `sub` bằng SHA-256 không mặc nhiên làm dữ liệu anonymous?
5. Hãy liệt kê các nơi cần rà soát khi chuyển từ public sang pairwise subject.

**Gợi ý đáp án:**

1. Hai sản phẩm có thể ghép lịch sử của cùng một người mà không cần chia sẻ tên/email; subject ổn định trở thành khóa theo dõi chéo hệ thống.
2. IdP cấp subject khác nhau theo sector, nên RP không thể join chỉ bằng `sub`. Nếu cần liên kết, phải có flow có mục đích và quyền rõ ràng.
3. Tạo dataset aggregate hoặc pseudonym riêng cho analytics bằng key/purpose riêng, phân quyền và retention; không tái sử dụng identifier của nghiệp vụ cho mọi bên.
4. Subject có thể thuộc không gian giá trị dễ đoán hoặc vẫn được đối chiếu qua dữ liệu khác; hash ổn định vẫn cho phép liên kết và có thể bị dò.
5. Mapping table, account linking, database keys, cache, session, logs, metrics, traces, queue/events, warehouse, export và backup.

## Ghi nhớ

- `sub` là định danh trong phạm vi issuer, không phải tên hiển thị và không phải token ID.
- Một mã giả danh vẫn có thể là dữ liệu cá nhân nếu có thể nhận diện hoặc liên kết với cá nhân.
- Pairwise subject giảm khả năng các RP độc lập liên kết người dùng; nó không phải anonymization và không chống mọi fingerprinting.
- JWT JWS được ký nhưng payload thường đọc được; chỉ phát hành claims thật sự cần cho audience.
- Bảo vệ subject trong log, metric, trace, cache, event, warehouse và backup; không ghi bearer token.
- Mapping, HMAC pseudonym và account linking đều cần purpose, access control, audit và retention.
- Quản lý vòng đời subject identifier cùng session, access token, refresh token, thu hồi và quy trình xóa dữ liệu.

### Tài liệu tham khảo

- [OpenID Connect Core 1.0 — Subject Identifier Types](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes)
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [GDPR — Regulation (EU) 2016/679, Article 4 and Recital 26](https://eur-lex.europa.eu/eli/reg/2016/679/oj)

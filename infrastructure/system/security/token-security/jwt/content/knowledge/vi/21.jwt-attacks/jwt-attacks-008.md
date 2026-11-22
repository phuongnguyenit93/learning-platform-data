# Cross-JWT confusion và thay token của ngữ cảnh khác

## 1. Hai vấn đề có liên quan nhưng không hoàn toàn giống nhau

JWT có thể được dùng cho nhiều mục đích: Access Token, ID Token, client assertion, JWT bearer assertion, DPoP proof, logout token hoặc credential nội bộ. Các token này đều có thể dùng chung định dạng JOSE, cùng cấu trúc header/payload và thậm chí cùng issuer hoặc khóa ký. Tuy nhiên, chúng không thể thay thế cho nhau.

**Cross-JWT confusion** xảy ra khi một hệ thống chấp nhận một JWT thuộc loại hoặc profile khác với loại mà endpoint đang mong đợi. Ví dụ, API chấp nhận ID Token như Access Token chỉ vì chữ ký hợp lệ và payload có subject.

**Token substitution** xảy ra khi một token hoặc artifact hợp lệ nhưng thuộc ngữ cảnh khác được thay vào vị trí của token/artifact mà giao dịch hiện tại yêu cầu. Ngữ cảnh khác có thể là người dùng, client, audience, tenant, môi trường, phiên đăng nhập hoặc một giao dịch OAuth/OIDC khác.

Hai vấn đề có thể xuất hiện cùng nhau. Một validator quá rộng có thể chấp nhận sai loại JWT, còn một luồng không ràng buộc token với giao dịch hiện tại có thể chấp nhận token đúng loại nhưng thuộc phiên khác.

Nguyên tắc cốt lõi là **xác minh đúng token cho đúng mục đích, đúng bên nhận và đúng giao dịch**. Chữ ký hợp lệ chỉ chứng minh dữ liệu được bảo vệ bởi khóa tương ứng; nó không chứng minh token phù hợp với endpoint đang xử lý.

Nội dung thuộc module Security - JSON Web Token (JWT), chương Tấn công JWT. Phạm vi áp dụng chung cho OAuth, OpenID Connect, JOSE và các hệ thống token khác, không phụ thuộc Java, Spring Security hay framework cụ thể.

## 2. JWT không tự nói nó được dùng vào mục đích nào

JWT là định dạng mang claims. Bản thân cấu trúc JWT không tự xác định một token là Access Token, ID Token hay assertion. Ý nghĩa đó đến từ token profile, issuer, audience, JOSE header, claims bắt buộc và hợp đồng của endpoint nhận.

Ví dụ, các token sau đều có thể là JWS hợp lệ:

| Loại JWT | Mục đích | Bên nhận dự kiến |
| --- | --- | --- |
| OAuth Access Token | Truy cập tài nguyên được cấp quyền | Resource Server |
| OpenID Connect ID Token | Truyền kết quả xác thực người dùng tới client OIDC | OIDC Client |
| Client Assertion | Xác thực OAuth client tại Authorization Server | Token Endpoint |
| JWT Bearer Assertion | Được dùng trong grant trao đổi assertion | Authorization Server |
| DPoP Proof JWT | Chứng minh client sở hữu khóa cho một request | Resource Server hoặc Authorization Server theo luồng |
| Logout Token | Thông báo sự kiện logout theo OIDC Back-Channel Logout | RP/Logout endpoint đã đăng ký |
| JWT nội bộ | Truyền context giữa các thành phần | Service được chỉ định trong hợp đồng nội bộ |

Một validator chỉ kiểm tra “JWT có chữ ký đúng” sẽ không phân biệt được các mục đích này. Nếu các token dùng chung issuer và khóa ký, nguy cơ nhầm lẫn càng lớn.

### 2.1. Token hợp lệ không có nghĩa là token phù hợp

Giả sử Identity Provider ký cả ID Token và Access Token bằng cùng một khóa. Một API nhận ID Token:

- Chữ ký có thể hợp lệ.
- Issuer có thể đúng.
- Subject có thể tồn tại.
- exp có thể còn hiệu lực.

Nhưng ID Token được phát hành cho OIDC Client để xác nhận sự kiện đăng nhập. Nó không mặc nhiên được phát hành cho API. Nếu audience là client_id thay vì resource identifier của API, API phải từ chối.

Vì vậy, validation phải bao gồm **token class/profile**, **audience** và các claims đặc trưng, không dừng ở chữ ký hoặc một vài claim chung.

## 3. Cross-JWT confusion hoạt động như thế nào?

Một hệ thống thường có nhiều endpoint nhận JWT. Nếu các endpoint dùng chung validator hoặc dùng quy tắc quá giống nhau, attacker có thể lấy token được cấp cho một mục đích rồi gửi sang mục đích khác.

~~~mermaid
flowchart TD
    A["Issuer ký nhiều loại JWT"] --> B["Access Token"]
    A --> C["ID Token"]
    A --> D["Client Assertion"]
    A --> E["DPoP Proof"]
    B --> F["API nhận token"]
    C --> F
    D --> F
    E --> F
    F --> G{"Validator chỉ kiểm tra chữ ký?"}
    G -- "Có" --> H["Có nguy cơ chấp nhận nhầm loại JWT"]
    G -- "Không" --> I["Kiểm tra profile, typ, iss, aud và claims riêng"]
    I --> J["Chỉ token đúng mục đích được chấp nhận"]
~~~

Cross-JWT confusion không đòi hỏi attacker phá chữ ký. Attacker chỉ cần tìm một JWT hợp lệ ở ngữ cảnh khác và một endpoint kiểm tra không đầy đủ.

Các điều kiện làm tăng nguy cơ:

- Nhiều loại JWT dùng chung issuer và signing key.
- Các loại token có tập claims giao nhau như iss, sub, aud, exp.
- Endpoint dùng chung một validator chung chung.
- Không kiểm tra typ hoặc token profile.
- Audience rộng hoặc bị bỏ qua.
- Không kiểm tra các claim chỉ có ở một profile.
- Validator chọn loại token dựa hoàn toàn vào dữ liệu header chưa xác minh.
- Một dịch vụ tin kết quả xác minh từ dịch vụ khác mà không bảo vệ identity context.

## 4. Tình huống 1: dùng ID Token thay cho Access Token

Đây là ví dụ điển hình của Cross-JWT confusion.

OIDC ID Token thường có:

- iss: OpenID Provider.
- sub: chủ thể đã xác thực.
- aud: OIDC Client nhận ID Token.
- exp và iat.
- nonce khi luồng yêu cầu.

OAuth Access Token được cấp cho Resource Server và có audience, scope, client và token profile theo chính sách OAuth. Hai token có thể cùng chứa iss, sub, exp và được cùng issuer ký, nhưng mục đích khác nhau.

Ví dụ ID Token:

~~~json
{
  "iss": "https://identity.example.org/",
  "sub": "user-123",
  "aud": "web-client-01",
  "exp": 1893456900,
  "iat": 1893456000,
  "nonce": "login-transaction-abc"
}
~~~

Nếu API hóa đơn chỉ kiểm tra chữ ký, iss và sub, nó có thể chấp nhận ID Token này dù audience dành cho web-client-01. Điều đó biến credential dành cho client thành credential truy cập API.

Phòng thủ:

1. API xác định audience riêng của chính nó.
2. API áp dụng Access Token profile mà nó hỗ trợ.
3. Nếu dùng RFC 9068, kiểm tra typ là at+jwt cùng các quy tắc profile.
4. Kiểm tra issuer, audience, claims bắt buộc, thời gian và scope.
5. Dùng validator OIDC riêng cho ID Token; không dùng validator ID Token tại Resource Server.

Không chỉ dựa vào tên claim hoặc việc ID Token có chứa scope tùy biến. Audience và token profile mới xác định token có dành cho API hay không.

## 5. Tình huống 2: dùng Access Token làm ID Token

Chiều ngược lại cũng nguy hiểm. Một client OIDC có thể nhận Access Token và nhầm nó với ID Token nếu chỉ decode payload, đọc sub hoặc tin chữ ký.

Access Token không thay thế bằng chứng xác thực theo OIDC. OIDC Client phải xác minh ID Token theo OpenID Connect Core, bao gồm issuer, audience là client_id, chữ ký, thời gian, nonce và các điều kiện theo flow.

Ví dụ:

| Kiểm tra | ID Token | Access Token |
| --- | --- | --- |
| Mục đích | Kết quả xác thực tới OIDC Client | Truy cập Resource Server |
| Audience | Client OIDC | Resource/API |
| Nonce | Kiểm tra theo Authentication Request khi áp dụng | Không phải cơ chế xác minh Access Token phổ quát |
| Scope | Không phải tiêu chí chính để xác minh đăng nhập | Quyền truy cập theo OAuth profile |
| Validator | OIDC ID Token validation | Access Token validation |

Nếu client dùng Access Token để tạo session đăng nhập mà không xác minh ID Token, nó có thể chấp nhận token được phát hành cho một API hoặc client khác.

## 6. Tình huống 3: nhầm Client Assertion, JWT Bearer Assertion và Access Token

OAuth có thể dùng JWT làm assertion tại Token Endpoint. Các assertion này có thể được ký bởi client hoặc issuer được tin cậy, nhưng chúng được phát hành để thực hiện một giao thức cụ thể.

Ví dụ, client assertion dùng để xác thực OAuth client. JWT Bearer Assertion có thể được dùng làm grant assertion. Các profile này có quy tắc riêng về iss, sub, aud, exp, jti, client identity và cách sử dụng.

Một Resource Server không được chấp nhận client assertion chỉ vì:

- Chữ ký hợp lệ bằng khóa của một client.
- Có sub hoặc client_id.
- Có exp còn hiệu lực.

Tương tự, Token Endpoint không được coi một Access Token là client assertion chỉ vì token đó do cùng issuer ký.

Phòng thủ:

- Token Endpoint chỉ chấp nhận assertion theo đúng grant/client-authentication profile đang xử lý.
- Audience của assertion phải phù hợp Token Endpoint theo profile.
- Subject/issuer/client binding phải đúng quy tắc của profile.
- jti và exp được kiểm tra khi profile yêu cầu; replay policy được áp dụng riêng.
- Resource Server dùng validator Access Token và audience của API.

Không dùng một hàm xác minh JWT chung rồi suy ra mọi token có chữ ký hợp lệ đều có thể được dùng tại mọi endpoint.

## 7. Tình huống 4: dùng DPoP Proof như Access Token

DPoP Proof là một JWT được client tạo cho một request để chứng minh quyền sở hữu private key. Nó không phải Access Token. Một proof hợp lệ có thể chứa htm, htu, iat, jti và public JWK; với access token ràng buộc DPoP, Resource Server còn kiểm tra cnf.jkt và ath theo RFC 9449.

Nếu API chấp nhận bất kỳ JWT ký hợp lệ nào làm Access Token, attacker có thể thử gửi DPoP proof tới endpoint API. Một proof có chữ ký hợp lệ vẫn chỉ chứng minh một request proof theo DPoP; nó không tự cấp quyền truy cập tài nguyên.

Validator cần phân biệt:

| Đặc điểm | Access Token | DPoP Proof |
| --- | --- | --- |
| Vai trò | Credential cấp quyền truy cập | Bằng chứng sở hữu khóa cho request |
| Bên phát hành/tạo | Authorization Server | Client tạo proof; proof không cần có claim iss |
| Header typ | Theo Access Token profile, ví dụ at+jwt trong RFC 9068 | dpop+jwt theo RFC 9449 |
| Audience/resource | Được xác minh theo Access Token profile | Ràng buộc bằng htu/method và ngữ cảnh DPoP |
| Claims đặc trưng | iss, aud, exp, sub, client_id, jti theo profile | htm, htu, iat, jti, ath/nonce khi áp dụng |

Không dùng DPoP proof như bearer token. Không dùng Access Token thay cho DPoP proof. Hai JWT có thể cùng xuất hiện trong một request nhưng phải được xác minh bằng hai quy trình riêng.

## 8. Tình huống 5: thay token giữa hai audience hoặc Resource Server

Một Access Token được cấp cho API A có thể có chữ ký hợp lệ và scope hợp lệ, nhưng không được dùng ở API B nếu audience không bao gồm B.

Ví dụ:

~~~json
{
  "iss": "https://identity.example.org/",
  "sub": "user-123",
  "aud": "https://api.example.org/invoices",
  "scope": "invoice:read",
  "exp": 1893456900
}
~~~

Attacker thay token dành cho API hồ sơ bằng token này tại API báo cáo. Nếu API báo cáo bỏ qua aud, nó có thể chấp nhận token sai recipient.

Phòng thủ:

- Mỗi Resource Server có audience identifier rõ ràng.
- So khớp aud chính xác theo profile.
- Không dùng iss, client_id hoặc scope thay cho aud.
- Không dùng token dành cho gateway ở mọi service phía sau.
- Dùng OAuth Token Exchange nếu cần credential mới cho downstream audience.

Mảng aud không tự động là lỗi. Resource Server phải kiểm tra đúng audience của mình và áp dụng chính sách multi-audience đã định nghĩa. Nếu API yêu cầu một audience duy nhất, phải từ chối token có recipient ngoài hợp đồng.

## 9. Tình huống 6: thay token giữa tenant, môi trường hoặc phiên

Ngay cả khi hai token cùng loại và cùng audience, chúng vẫn có thể thuộc ngữ cảnh khác.

### 9.1. Tenant substitution

Một token được cấp trong tenant A bị thay vào request đang truy cập dữ liệu tenant B. Nếu hệ thống chỉ kiểm tra chữ ký và role chung mà bỏ qua tenant binding, token có thể bị dùng chéo tenant.

Phải đối chiếu tenant đã xác minh với tenant context được xác định từ nguồn tin cậy. Không lấy tenant chưa xác minh từ payload để tự chọn database hoặc schema.

### 9.2. Environment substitution

Token từ development hoặc staging bị gửi tới production. Nếu các môi trường dùng chung issuer, key và audience quá rộng, token thử nghiệm có thể được chấp nhận ở production.

Phòng thủ:

- Tách issuer hoặc trust configuration theo môi trường khi phù hợp.
- Dùng audience identifier riêng cho production, staging và development.
- Tách khóa ký và quyền truy cập JWKS nếu kiến trúc cho phép.
- Không để production tin cậy khóa hoặc issuer thử nghiệm.

### 9.3. Session substitution

Token cũ hoặc token thuộc một phiên khác có thể được thay vào request hiện tại. Nếu ứng dụng yêu cầu ràng buộc với session, client hoặc transaction, cần kiểm tra session identifier, nonce, jti hoặc trạng thái grant theo profile.

Không coi cùng sub là cùng một phiên. Một người dùng có thể có nhiều phiên và nhiều token với quyền, thời hạn hoặc trạng thái khác nhau.

## 10. Tình huống 7: thay token giữa các giao dịch OIDC

OIDC có các cơ chế ràng buộc phản hồi với Authentication Request:

- **state** giúp client liên kết Authorization Response với request đã khởi tạo và chống CSRF theo thiết kế luồng.
- **nonce** ràng buộc ID Token với Authentication Request.
- **c_hash** ràng buộc Authorization Code với ID Token trong các trường hợp Hybrid Flow yêu cầu.
- **at_hash** ràng buộc Access Token với ID Token trong các trường hợp flow yêu cầu.
- **PKCE** ràng buộc việc đổi Authorization Code với code_verifier của client.

Nếu client chỉ xác minh chữ ký ID Token mà không kiểm tra nonce, ID Token từ một giao dịch đăng nhập khác có thể bị đưa vào phiên hiện tại. Nếu Code hoặc Access Token bị tráo giữa phản hồi, hash claim hoặc PKCE có thể phát hiện sự không nhất quán tùy flow.

Không phải mọi flow đều bắt buộc at_hash và c_hash. Client phải xác định đúng response_type và endpoint phát hành ID Token trước khi áp dụng điều kiện REQUIRED/OPTIONAL theo OIDC Core.

## 11. Vì sao dùng chung khóa ký làm tăng nguy cơ?

Nếu một issuer dùng cùng khóa ký cho Access Token, ID Token, assertion và JWT nội bộ, chữ ký không phân biệt được mục đích của token. Một validator yếu có thể xác minh thành công tất cả các token này.

Key separation có thể giảm nguy cơ:

- Dùng khóa riêng cho các token class hoặc trust domain khi kiến trúc cho phép.
- Gắn mỗi khóa với issuer, mục đích và thuật toán được phép.
- Không dùng cùng key resolver toàn cục cho mọi loại JWT.
- Không chọn key chỉ dựa trên kid do token cung cấp; kid chỉ là gợi ý trong kho khóa tin cậy.
- Không lấy jku/x5u từ token chưa xác minh để tải khóa tùy ý.

Tuy nhiên, tách khóa không thay thế token profile validation. Một Access Token được ký bằng khóa riêng vẫn có thể bị dùng nhầm nếu API khác chấp nhận sai audience hoặc bỏ qua profile.

## 12. Explicit Typing và mutually exclusive validation rules

RFC 8725 khuyến nghị phân biệt rõ các loại JWT và dùng validation rules loại trừ lẫn nhau để tránh Cross-JWT confusion.

### 12.1. Explicit Typing

JOSE Header parameter **typ** có thể chỉ định media type hoặc loại nội dung JWT. Một profile có thể quy định giá trị cụ thể, ví dụ:

| Token profile | Giá trị typ minh họa/được profile quy định |
| --- | --- |
| JWT Access Token theo RFC 9068 | at+jwt |
| DPoP Proof theo RFC 9449 | dpop+jwt |
| JWT profile nội bộ | Một media type riêng đã được các bên thống nhất |

Không giả định mọi ID Token đều phải có một typ riêng phổ quát. OIDC Core có quy tắc xác minh ID Token riêng; việc dùng typ bổ sung phải phù hợp profile và khả năng liên thông.

typ chỉ là một thành phần của validation. Nó không thay thế chữ ký, issuer, audience hoặc claims bắt buộc. Validator cũng không được chọn policy chỉ vì token tự khai typ nào; endpoint và cấu hình tin cậy phải xác định loại token mong đợi trước, sau đó typ đã được bảo vệ bằng JOSE phải khớp policy.

### 12.2. Mutually Exclusive Validation Rules

Mỗi loại JWT cần một tập quy tắc đủ khác biệt để token của profile khác không thể vượt qua validator đó.

Ví dụ:

| Quy tắc | Access Token | ID Token | Client Assertion | DPoP Proof |
| --- | --- | --- | --- | --- |
| Endpoint | Resource Server | OIDC Client callback/token response | Token Endpoint | Resource Server hoặc Authorization Server |
| Audience | Resource/API | OIDC Client | Token Endpoint theo profile | Request URI/method binding theo DPoP |
| Token type | at+jwt nếu RFC 9068 | Theo OIDC validation | Theo assertion profile | dpop+jwt |
| Claims đặc trưng | scope/client_id/jti theo profile | nonce/auth_time/azp khi áp dụng | iss/sub/aud/exp/jti theo profile | htm/htu/iat/jti/ath/nonce khi áp dụng |
| Mục tiêu | Truy cập API | Xác nhận đăng nhập | Xác thực client hoặc grant | Chứng minh sở hữu khóa |

Một validator phải từ chối token thiếu dấu hiệu đặc trưng hoặc có audience sai, ngay cả khi chữ ký đúng.

### 12.3. cty không thay typ

JOSE Header parameter **cty** mô tả content type của payload, đặc biệt hữu ích khi payload là một JWT lồng bên trong JOSE object khác. Giá trị cty như JWT cho biết nội dung là JWT lồng; nó không tự xác định token bên trong là Access Token, ID Token hay assertion.

Không dùng cty thay cho typ hoặc token profile. Với nested JWT, phải xác minh đầy đủ từng lớp theo hợp đồng.

## 13. Chọn validator từ endpoint, không từ token chưa xác minh

Một thiết kế an toàn bắt đầu từ ngữ cảnh nhận token:

1. Endpoint hoặc giao thức xác định token class mong đợi.
2. Cấu hình tin cậy chọn issuer, audience, key set, algorithm allowlist và profile.
3. Token được parse trong giới hạn tài nguyên.
4. Header chưa xác minh chỉ dùng để kiểm tra sơ bộ hoặc tìm candidate key trong trust configuration cố định.
5. Xác minh chữ ký/MAC hoặc authenticated decryption.
6. Kiểm tra typ và token profile sau khi header đã được bảo vệ mật mã.
7. Kiểm tra iss, aud, sub, thời gian và claims bắt buộc.
8. Kiểm tra nonce, jti, session, tenant, client hoặc binding theo profile.
9. Chỉ tạo context đã xác minh nếu toàn bộ validation bắt buộc thành công.

Không dùng claim iss chưa xác minh để tự discovery issuer mới. Không dùng typ chưa xác minh để chuyển token sang một validator có quyền rộng hơn. Không dùng kid để lấy khóa từ một nguồn tùy ý.

## 14. Mã giả chống Cross-JWT confusion

~~~text
function validateTokenForEndpoint(rawToken, endpointContext):
    expectedProfile = trustedPolicyRegistry.profileFor(endpointContext)
    require expectedProfile exists

    parsed = strictParseJwtWithinLimits(rawToken)
    untrustedHeader = parsed.protectedHeader

    require untrustedHeader.alg in expectedProfile.allowedAlgorithms
    candidateKey = expectedProfile.trustedKeySet.find(untrustedHeader.kid)
    require candidateKey exists
    require candidateKey is compatible with untrustedHeader.alg

    cryptographicResult = verifyAccordingToProfile(
        rawToken,
        candidateKey,
        expectedProfile
    )
    require cryptographicResult is valid

    header = cryptographicResult.protectedHeader
    claims = cryptographicResult.verifiedClaims

    require header.typ matches expectedProfile.requiredTyp
    require claims.iss exactly equals expectedProfile.issuer
    require validateAudience(claims.aud, expectedProfile)
    require validateRequiredClaimsAndTypes(claims, expectedProfile)
    require validateTimeClaims(claims, expectedProfile)
    require validateProfileSpecificRules(claims, header, expectedProfile)

    if expectedProfile.requiresTransactionBinding:
        require validateNonceStateHashOrPkce(claims, endpointContext)

    if expectedProfile.requiresSenderConstraint:
        require validateProofOfPossession(endpointContext, claims)

    return createImmutableContext(
        profile = expectedProfile.id,
        issuer = claims.iss,
        audience = claims.aud,
        subject = claims.sub,
        permittedClaims = selectAllowedClaims(claims, expectedProfile)
    )
~~~

Đây là pseudocode khái quát. Không phải profile nào cũng có typ bắt buộc hoặc cùng tập claims. expectedProfile phải đến từ endpoint/configuration tin cậy; requiredTyp chỉ được cấu hình khi profile quy định. Các kiểm tra nonce, hash, PKCE và sender constraint chỉ áp dụng theo giao thức tương ứng.

## 15. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Chỉ xác minh chữ ký | JWT đúng chữ ký nhưng sai mục đích vẫn được chấp nhận | Kiểm tra profile, issuer, audience và claims |
| Dùng ID Token làm Access Token | OIDC credential bị dùng để truy cập API | Validator riêng và audience của Resource Server |
| Dùng Access Token làm ID Token | Bỏ qua xác minh OIDC login | Xác minh ID Token theo OIDC Core |
| Dùng Client Assertion làm Access Token | Assertion tại Token Endpoint bị dùng ở API | Audience và validator theo từng endpoint |
| Dùng DPoP Proof làm Access Token | Proof-of-possession bị hiểu thành credential cấp quyền | Validator DPoP riêng |
| Dùng một validator cho mọi JWT | Các profile có quy tắc giao nhau | Mutually exclusive validation rules |
| Bỏ qua aud | Token của resource khác được chấp nhận | Audience riêng cho mỗi Resource Server |
| Bỏ qua nonce/state/PKCE | Token hoặc Code từ giao dịch khác có thể bị ghép vào | Ràng buộc transaction theo OIDC/OAuth |
| Chọn validator theo typ chưa xác minh | Token có thể điều khiển đường xác minh | Chọn profile từ endpoint tin cậy |
| Dùng chung khóa cho mọi token class mà không tách profile | Chữ ký không giúp phân biệt mục đích | Key separation kết hợp profile validation |
| Tin kid/jku/x5u tùy ý | Có thể chọn hoặc tải khóa ngoài trust boundary | Chỉ dùng trust store đã cấu hình |
| Coi cty là token type | Nhầm định dạng payload với mục đích token | Phân biệt cty, typ và profile |
| Tin token của gateway tại mọi service | Token bị dùng chéo service | Audience riêng hoặc token exchange |
| Dùng sub giống nhau làm bằng chứng cùng phiên | Token của phiên khác được chấp nhận | Kiểm tra nonce/session/grant context |

## 16. Ma trận kiểm thử Cross-JWT confusion và substitution

| Nhóm | Ca kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| Token class | ID Token gửi tới API | Từ chối |
| Token class | Access Token gửi tới OIDC callback làm ID Token | Từ chối |
| Token class | Client Assertion gửi tới Resource Server | Từ chối |
| Token class | DPoP Proof gửi như bearer Access Token | Từ chối |
| Audience | Token của API A gửi tới API B | Từ chối |
| Issuer | Token từ issuer khác nhưng dùng khóa/format tương tự | Từ chối |
| Tenant | Token tenant A dùng trong context tenant B | Từ chối |
| Environment | Token staging gửi tới production | Từ chối |
| Transaction | ID Token từ login transaction khác | Nonce/state binding không khớp, từ chối |
| Artifact | Access Token/Code bị thay trong OIDC response | at_hash/c_hash mismatch nếu flow yêu cầu, từ chối |
| PKCE | Code từ giao dịch khác hoặc verifier sai | Token Endpoint từ chối |
| Explicit typing | typ sai hoặc thiếu khi profile yêu cầu | Từ chối |
| Required claims | Token profile khác thiếu claim đặc trưng | Từ chối |
| Key separation | Token ký bằng key của profile khác | Từ chối theo key/profile policy |
| Nested JWT | Lớp ngoài hợp lệ nhưng lớp JWT bên trong sai | Từ chối toàn bộ |
| Header trust | kid/jku/iss chưa xác minh trỏ tới nguồn ngoài | Không truy cập nguồn tùy ý |
| Replay | jti hoặc proof đã được sử dụng trong profile one-time | Từ chối theo replay policy |

Kiểm thử nên bao gồm cả token có chữ ký hợp lệ nhưng sai loại. Đây là cách chứng minh validator thực sự phân biệt profile thay vì chỉ kiểm tra mật mã.

## 17. Checklist phòng thủ

1. [ ] Mỗi endpoint xác định trước token class/profile mà nó chấp nhận.
2. [ ] Không dùng một validator chung chỉ kiểm tra chữ ký cho mọi JWT.
3. [ ] Dùng explicit typing khi profile hỗ trợ và quy định giá trị typ rõ ràng.
4. [ ] Validation rules của Access Token, ID Token, assertion, DPoP proof và JWT nội bộ loại trừ lẫn nhau.
5. [ ] Issuer được so khớp chính xác với trust configuration.
6. [ ] Audience được kiểm tra theo đúng Resource Server hoặc client nhận.
7. [ ] Algorithm allowlist, key type và key usage gắn với profile.
8. [ ] kid chỉ tìm khóa trong trust store đã cấu hình; không tải jku/x5u tùy ý.
9. [ ] Kiểm tra claims bắt buộc, kiểu dữ liệu, thời gian và semantics riêng của profile.
10. [ ] OIDC transaction kiểm tra state, nonce, at_hash/c_hash khi flow yêu cầu.
11. [ ] Authorization Code được ràng buộc bằng PKCE khi áp dụng.
12. [ ] Tenant, client, session, environment và resource context được kiểm tra độc lập.
13. [ ] Nested JWT được xác minh đầy đủ từng lớp; không nhầm typ với cty.
14. [ ] Token được dùng đúng endpoint; Refresh Token, Access Token, ID Token và assertion không thay thế nhau.
15. [ ] Context đã xác minh chỉ được tạo sau khi toàn bộ validation bắt buộc thành công.
16. [ ] Có negative tests cho token đúng chữ ký nhưng sai profile, audience hoặc transaction.

## 18. Tài liệu tiêu chuẩn liên quan

- **RFC 8725 — JSON Web Token Best Current Practices:** Cross-JWT confusion, explicit typing và mutually exclusive validation rules.
- **RFC 7519 — JSON Web Token (JWT):** cấu trúc JWT, claims và recipient.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** Access Token profile, typ at+jwt và quy tắc Resource Server.
- **OpenID Connect Core 1.0:** ID Token validation, nonce, audience và ràng buộc artifact theo flow.
- **RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants:** JWT assertion tại Token Endpoint.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** DPoP proof JWT và ràng buộc request.
- **RFC 8693 — OAuth 2.0 Token Exchange:** cấp token mới cho resource/actor đích theo policy.

**Nguyên tắc ghi nhớ:** Một JWT có thể hoàn toàn hợp lệ về chữ ký nhưng vẫn sai mục đích hoặc sai giao dịch. Cross-JWT confusion được ngăn bằng profile rõ ràng và validation rules loại trừ lẫn nhau; token substitution được ngăn bằng issuer, audience, tenant/session binding và cơ chế transaction như nonce, state, PKCE, at_hash hoặc c_hash khi áp dụng. Hãy để endpoint quyết định token nào được chấp nhận, rồi xác minh đầy đủ token theo đúng hợp đồng đó.

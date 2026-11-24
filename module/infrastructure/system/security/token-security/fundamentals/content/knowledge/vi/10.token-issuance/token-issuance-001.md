# Điều kiện để phát hành token

Một người dùng vừa nhập đúng mật khẩu. Hệ thống có nên lập tức phát hành access token với quyền quản trị cho mọi API hay không? **Không.** Xác thực thành công chỉ trả lời một phần câu hỏi về danh tính. Để phát hành token an toàn, **Authorization Server** còn cần biết yêu cầu đến từ client nào, client được phép dùng loại grant gì, chủ thể hoặc ủy quyền nào đã được kiểm tra, token được cấp cho tài nguyên nào, có phạm vi quyền nào, sống bao lâu và có ràng buộc bảo mật nào.

Bài thuộc chương **Token issuance** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Trọng tâm là **điều kiện trước khi phát hành** access token, refresh token và OIDC ID token trong những luồng phổ biến của OAuth 2.0/OpenID Connect (OIDC); đồng thời liên hệ định dạng JWT/opaque, claims, scope, audience, lưu trữ, thu hồi và phòng chống việc token bị đánh cắp hoặc phát lại.

Sau bài này, bạn có thể phân tích một yêu cầu cấp token thành các bước kiểm tra, phân biệt điều kiện của Authorization Code + PKCE, Client Credentials và Refresh Token grant, thiết kế một chính sách phát hành có đặc quyền tối thiểu, và nhận diện những tình huống phải **từ chối hoặc thu hẹp quyền**.

## 1. Phát hành token là một quyết định tin cậy có điều kiện

**Phát hành token (token issuance)** là hành động Authorization Server tạo và trao một credential có hiệu lực theo chính sách cho client. Người có token sau đó có thể thực hiện hành động trong phạm vi mà bên nhận chấp nhận. Với **bearer access token**, việc đánh cắp nguyên chuỗi token có thể đủ để sử dụng lại trong thời gian hiệu lực nếu không có cơ chế ràng buộc chủ sở hữu token.

Một chính sách phát hành có thể tóm lược bằng biểu thức:

~~~text
Issue token IF
    request hợp lệ theo giao thức
    AND client được nhận diện và được phép dùng grant
    AND bằng chứng của grant được xác minh, còn hiệu lực, đúng client
    AND chủ thể/ủy quyền đủ tin cậy theo yêu cầu flow
    AND requested scope/resource nằm trong quyền được phép cấp
    AND ràng buộc audience, thời hạn, loại token được thỏa mãn
    AND khóa, nơi phát hành và các kiểm soát bảo mật còn đáng tin
ELSE deny hoặc yêu cầu bổ sung điều kiện
~~~

Đây là **mô hình tư duy**, không phải công thức chuẩn dùng nguyên xi trong mọi triển khai. Quyết định cuối cùng còn phụ thuộc loại grant, kiểu client, profile, chính sách rủi ro, sự đồng ý của người dùng khi cần và trạng thái tài khoản/ủy quyền hiện hành.

**Không phải lần phát hành nào cũng có người dùng đăng nhập.** Ví dụ, với **Client Credentials grant**, token được cấp dựa trên quyền của ứng dụng/dịch vụ, không đại diện một phiên đăng nhập người dùng. Với **Refresh Token grant**, server kiểm tra credential và ủy quyền đã có trước đó mà không mặc định yêu cầu nhập mật khẩu ở mỗi lần làm mới.

### Thành phần và trách nhiệm

| Thành phần | Vai trò trong quá trình cấp token |
|---|---|
| **Client** | Đăng ký với Authorization Server, chọn flow được phép, gửi yêu cầu ủy quyền/đổi token, bảo vệ credential của mình |
| **Resource Owner / End User** | Khi flow có người dùng: xác thực và ủy quyền quyền truy cập theo chính sách, có thể xác nhận consent |
| **Authorization Server (AS)** | Xác minh client, grant, chủ thể, quyền cấp, resource; phát hành và quản lý vòng đời token |
| **Resource Server (RS)** | Kiểm tra access token khi nhận, xác minh audience/scope và thực thi quyền trên tài nguyên; không tin token chỉ vì client nói đã đăng nhập |
| **Trust/key infrastructure** | Bảo vệ signing key, public key/JWKS, secret, hệ thống lưu trạng thái và metadata issuer |

Phân biệt rõ **phát hành** với **sử dụng token**: AS có trách nhiệm chỉ cấp những quyền thích hợp; RS vẫn phải đánh giá quyền thực tế cho một API và tài nguyên cụ thể. Một access token được cấp đúng không có nghĩa người gọi được đọc mọi đơn hàng hoặc thao tác trên mọi tenant.

## 2. Xác định loại token và flow trước khi đặt điều kiện

Không có một điều kiện phát hành duy nhất cho mọi token. Phải xác định **grant** và **mục đích token**:

| Flow hoặc thao tác | Bằng chứng chính cần kiểm tra | Kết quả có thể được cấp | Điểm cần tránh |
|---|---|---|---|
| **Authorization Code + PKCE** | Authorization code đúng client và redirect URI, PKCE verifier, trạng thái đăng nhập/ủy quyền | Access token; refresh token khi chính sách cho phép; ID token nếu là flow OIDC phù hợp | Chấp nhận code bị dùng lại, sai verifier hoặc code của client khác |
| **Client Credentials** | Danh tính và xác thực confidential client phù hợp, quyền client với API/scope | Access token đại diện quyền của client/dịch vụ | Tự suy diễn có end user hoặc cấp quyền thay mặt mọi người dùng |
| **Refresh Token grant** | Refresh token còn hiệu lực, gắn với client, không bị thu hồi/tái sử dụng trái phép, quyền gốc vẫn cho phép | Access token mới; có thể refresh token mới theo chính sách rotation | Nâng scope/audience vượt quyền gốc; tiếp tục cấp khi refresh token bị thu hồi |
| **Token Exchange khi triển khai** | Quyền trao đổi, subject token/actor token đáng tin, đối tượng nhận và quyền ủy nhiệm | Token mới cho Resource Server khác theo chính sách | Xem token đầu vào là giấy phép đổi sang mọi audience |

Trong OIDC, **ID token** là chứng cứ xác thực danh tính dành cho **client/Relying Party** và có bộ điều kiện/claims khác access token. **Refresh token** dùng để xin cấp token mới tại AS; nó không phải credential gửi đến Resource Server. **JWT** và **opaque** mô tả biểu diễn/cách xác minh, còn **access/refresh/ID** mô tả mục đích. Không được suy quyền phát hành chỉ từ tên hay hình dạng chuỗi token.

## 3. Điều kiện của Authorization Code Flow với PKCE

Đây là flow phổ biến cho ứng dụng có người dùng, đặc biệt khi cần tách việc tương tác đăng nhập tại Authorization Server khỏi việc client lấy token từ token endpoint.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>C: Bắt đầu đăng nhập
    C->>AS: Authorization request + PKCE challenge
    AS->>U: Xác thực, kiểm quyền/consent khi cần
    U-->>AS: Hoàn thành bước được yêu cầu
    AS-->>C: Authorization code gắn với client/redirect
    C->>AS: Token request + code + code_verifier
    AS->>AS: Kiểm code, client, redirect, PKCE, quyền cấp
    AS-->>C: Access token và token khác nếu được phép
    C->>RS: Bearer access token
    RS->>RS: Xác minh token, audience và policy
    RS-->>C: Kết quả được phép
~~~

### 3.1. Kiểm tra trước khi tạo authorization code

AS cần xác định yêu cầu dùng **response type và client** được đăng ký/chấp nhận; redirect URI hợp lệ theo quy tắc so khớp an toàn; scope/resource hợp lệ; các yêu cầu bổ sung như PKCE, OIDC nonce hoặc xác thực mạnh được đáp ứng theo profile và chính sách.

Người dùng phải được xác thực với mức tin cậy phù hợp hành động. Với truy cập nhạy cảm, có thể yêu cầu **MFA hoặc step-up authentication**, kiểm tra độ mới xác thực, trạng thái tài khoản và rủi ro phiên. Nếu cần consent/ủy quyền của resource owner, AS phải xử lý đúng quyền được chấp thuận; **consent không mặc nhiên phải xuất hiện ở mọi phiên hoặc mọi loại grant**.

**PKCE** ràng buộc authorization code với một bí mật tạm thời do client tạo:

- Client tạo **code_verifier** ngẫu nhiên đủ entropy và gửi **code_challenge** được dẫn xuất, thường dùng phương thức **S256**, trong authorization request.
- Client giữ code_verifier, không đưa nó vào authorization request.
- Tại token endpoint, client gửi code_verifier; AS kiểm tra nó khớp code_challenge đã gắn với authorization code.

Kết quả là **chỉ biết authorization code** thường không đủ để đổi lấy token nếu không có verifier. PKCE giảm rủi ro code interception nhưng **không thay thế** redirect URI validation, chống CSRF của client, TLS, bảo vệ client hoặc xác thực confidential client khi cần.

### 3.2. Kiểm tra tại token endpoint khi đổi code

Authorization code là bằng chứng **ngắn hạn, một lần**, được gắn với client và redirect URI (nếu có trong yêu cầu ban đầu) cùng các thuộc tính cấp quyền. AS cần kiểm tra:

1. **Grant type hợp lệ:** client được dùng authorization_code.
2. **Client binding:** code được cấp cho chính client đang đổi. Confidential client phải được xác thực theo cấu hình; public client không được giả vờ có secret bảo mật.
3. **Redirect binding:** redirect URI được đối chiếu với URI gắn trong authorization code theo yêu cầu của giao thức/profile.
4. **PKCE:** code_verifier hợp lệ và khớp challenge đã lưu; thất bại phải từ chối.
5. **Hiệu lực của code:** code chưa hết hạn, chưa bị đổi trước đó, không bị vô hiệu hóa; một code bị dùng lại không được cấp token lần nữa.
6. **Bằng chứng ủy quyền:** grant, chủ thể, scope/resource và điều kiện xác thực vẫn có thể được chấp nhận theo chính sách của AS.

Ví dụ một **token request dạng biểu diễn rút gọn**:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<one-time-code>&redirect_uri=https%3A%2F%2Fapp.example.org%2Fcallback&client_id=shop-web&code_verifier=<pkce-verifier>
~~~

Đây chỉ là ví dụ **public client** minh họa. Trong hệ thống thực tế, confidential client phải xác thực theo phương thức đã đăng ký; nội dung token request, redirect URI và hỗ trợ PKCE phụ thuộc profile đang dùng. Không đặt authorization code, verifier hoặc credential thật vào log.

### 3.3. Vì sao chỉ “đăng nhập thành công” chưa thể cấp mọi token?

Một người dùng có thể xác thực đúng nhưng:

- client chưa được cấp quyền truy cập tài nguyên được yêu cầu;
- client cố xin scope rộng hơn quyền người dùng đã chấp thuận;
- request có redirect URI không hợp lệ;
- code được cấp cho một client khác;
- PKCE verifier không khớp;
- người dùng bị khóa hoặc một bước step-up chưa đáp ứng;
- phiên/ủy quyền bị hủy trước khi đổi code.

Với các trường hợp này, AS phải **từ chối hoặc yêu cầu đáp ứng điều kiện còn thiếu**, chứ không cấp token rộng rồi trông chờ Resource Server tự sửa sai hoàn toàn.

## 4. Điều kiện phát hành trong Client Credentials grant

**Client Credentials** dành cho trường hợp client truy cập tài nguyên bằng quyền của **chính nó**. Thường áp dụng cho backend, job, service-to-service với confidential client được xác thực. Luồng này **không mặc nhiên có người dùng cuối, màn hình đăng nhập hay consent của người dùng**.

Ví dụ một dịch vụ báo cáo định kỳ cần gọi Reports API:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <encoded-client-credentials>

grant_type=client_credentials&scope=reports:read
~~~

Ví dụ chỉ minh họa kiểu xác thực client bằng Basic; triển khai có thể dùng private_key_jwt, mTLS hoặc phương pháp khác theo chính sách. Các giá trị thật của client secret phải được giữ trong secret manager/kênh bảo mật, không ghi cứng hoặc xuất vào tracing.

Trước khi cấp token, AS cần kiểm tra:

1. Client được **đăng ký, nhận diện và xác thực** đúng phương pháp cho loại grant.
2. Client được phép dùng **client_credentials** và còn hoạt động; credential chưa bị thu hồi.
3. Scope được yêu cầu nằm trong quyền đã cấp cho **client**, không phải quyền chung của một user tình cờ có tên trong request.
4. Resource/audience được phép theo chính sách cấp token.
5. Thời hạn và điều kiện ràng buộc token phù hợp độ nhạy cảm của API.

Access token phát hành có thể có **sub** đại diện client hoặc định danh dịch vụ theo profile. Resource Server phải hiểu đó là **machine principal** và áp dụng policy dành cho máy. Không tự coi sub là một người dùng đang đăng nhập hoặc cho phép đọc dữ liệu của mọi user.

Ví dụ: Client có quyền **reports:read** và được cấp audience **reports-api**. Một token như vậy **không** có quyền gọi **payments-api** hoặc duyệt hoàn tiền chỉ vì cùng issuer. Với Client Credentials, cấp refresh token thông thường **không cần thiết** vì client có thể xác thực lại để xin access token; các profile/AS có thể có quy tắc riêng, nhưng không coi refresh token là kết quả mặc định.

## 5. Điều kiện phát hành lại bằng Refresh Token grant

**Refresh token** là credential dài hạn hơn theo chính sách để client xin access token mới tại Authorization Server, thường không phải tương tác lại với người dùng trên mỗi lần đổi. Đây là mục tiêu hấp dẫn với kẻ tấn công: người nắm refresh token có thể tiếp tục xin token nếu nó chưa bị thu hồi và chưa được bảo vệ bằng cơ chế ràng buộc bổ sung.

Ví dụ request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token-value>&client_id=shop-web
~~~

Đây là ví dụ public client. Confidential client phải xác thực; public client có thể được bảo vệ bởi **refresh token rotation** hoặc sender-constraining theo yêu cầu profile và chính sách. Chỉ có client_id trong request **không đủ xác thực một public client**.

AS phải kiểm tra ít nhất:

- Refresh token được nhận biết, chưa hết hạn hoặc bị vô hiệu hóa, có trạng thái cho phép sử dụng.
- Refresh token được **gắn với đúng client** và cơ chế bảo vệ client phù hợp được đáp ứng.
- Quyền/ủy quyền gốc còn hiệu lực và không bị thay đổi theo cách cấm làm mới; chính sách người dùng/tài khoản vẫn cho phép.
- Scope được yêu cầu không vượt quá scope đã được cấp trong grant gốc. Nếu scope được thu hẹp, access token mới phản ánh phạm vi hợp lệ.
- Audience/resource xin mới nằm trong quyền và ràng buộc đã được cấp; không mặc nhiên đổi refresh token lấy token cho **API tùy ý**.
- Nếu dùng rotation, lần đổi hợp lệ có thể phát refresh token mới và vô hiệu hóa token cũ một cách **nhất quán/atomic**.

### Rotation và phát hiện tái sử dụng

Với **refresh token rotation**, mỗi lần đổi thành công có thể tạo refresh token mới và khiến token trước đó không còn hợp lệ. Nếu token cũ xuất hiện lại, AS cần xử lý như dấu hiệu khả nghi về rò rỉ hoặc lỗi đồng bộ, áp dụng chính sách phát hiện **reuse** và có thể thu hồi cả **token family** để chặn kẻ tấn công tiếp tục làm mới.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant AS as Authorization Server
    C->>AS: RT1 hợp lệ + yêu cầu đổi token
    AS->>AS: Kiểm client, quyền, trạng thái RT1
    AS->>AS: RT1 -> invalid; tạo AT2 + RT2
    AS-->>C: AT2 + RT2
    C->>AS: RT1 cũ bị dùng lại
    AS->>AS: Phát hiện reuse và áp dụng policy
    AS-->>C: Từ chối, có thể thu hồi cả family
~~~

AS phải xử lý cạnh tranh giữa các yêu cầu đổi token cùng lúc theo chính sách đã xác định. Việc chỉ ghi “đã sử dụng” sau khi phát token mà không có kiểm soát đồng thời có thể khiến cùng refresh token được đổi nhiều lần.

**Thu hồi refresh token không tự xóa hiệu lực access token đã phát hành.** Nếu JWT access token được Resource Server xác minh hoàn toàn tại chỗ, token có thể còn được nhận đến thời điểm hết hạn trừ khi có cơ chế thu hồi bổ sung. Đó là một đánh đổi của vòng đời token.

## 6. Scope, audience và quyền cấp: phát đúng quyền cho đúng tài nguyên

Với một yêu cầu token, AS phải phân biệt:

- **Requested scope**: client yêu cầu quyền gì.
- **Granted scope**: AS thực sự được phép cấp theo client, chủ thể, consent và chính sách.
- **Requested resource/audience**: client muốn sử dụng token ở đâu.
- **Approved resource/audience**: AS cho phép token dùng tại API nào.
- **Quyền nghiệp vụ hiện hành**: Resource Server kiểm tra thêm đối với bản ghi và thao tác cụ thể.

Ví dụ hệ thống có:

| Resource Server | Audience ID | Scope hợp lệ |
|---|---|---|
| Orders API | orders-api | orders:read, orders:write |
| Payments API | payments-api | payments:read, payments:charge |
| Reports API | reports-api | reports:read |

Client **shop-web** yêu cầu **orders:read payments:charge** với audience **orders-api**. AS phải đánh giá yêu cầu theo quyền client và người dùng. Không được suy rằng scope thuộc Payments API có thể dùng ở Orders API, hoặc rằng client có một scope đọc thì được thêm scope charge. AS có thể **thu hẹp scope được cấp** theo quy định của giao thức/hợp đồng, hoặc từ chối yêu cầu không hợp lệ; client phải đọc phạm vi thực sự được trả về và API phải tự kiểm tra.

**OAuth 2.0 Resource Indicators (RFC 8707)** cung cấp tham số **resource** để client chỉ ra tài nguyên mong muốn khi AS hỗ trợ. Điều này hỗ trợ cấp access token có audience giới hạn, giảm khả năng một token bị dùng nhầm ở API khác. AS vẫn phải quyết định resource được phép; request của client **không phải bằng chứng cấp quyền**.

Một token tốt cho Orders API nên có **aud=orders-api** và scope đủ tối thiểu cho thao tác, thay vì token một lần dùng cho nhiều API không cần thiết. Token nhiều audience có thể hợp lệ trong một số profile, nhưng làm phạm vi ảnh hưởng khi bearer token bị đánh cắp rộng hơn, nên chỉ cấp khi có lý do nghiệp vụ và policy rõ ràng.

**Audience không thay cho phân quyền trên tài nguyên.** Token có aud=orders-api và scope=orders:read vẫn không tự cho phép xem đơn hàng của tenant khác. Resource Server phải đánh giá ownership, membership, role, trạng thái đơn hàng và quyền hiện hành.

## 7. Điều kiện phát hành phụ thuộc dạng token

Sau khi quyết định **có được phép cấp**, AS phải quyết định **cấp cái gì**. Mỗi dạng token có yêu cầu tạo, ký, bảo vệ và quản lý khác nhau.

### 7.1. JWT access token tự chứa

Nếu AS phát hành JWT access token, cần có khóa ký đang được tin cậy, thuật toán được phép và một profile claims phù hợp. Một payload minh họa theo hướng **JWT access token profile (RFC 9068)**:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1899999000,
  "exp": 1900000800,
  "jti": "example-id-847"
}
~~~

Đây chỉ là JSON minh họa, **chưa phải access token hoàn chỉnh**. RFC 9068 quy định các claims bắt buộc và header token theo profile, trong đó có **iss, sub, aud, client_id, iat, exp, jti**. Các ứng dụng có profile riêng phải xác định hợp đồng tương thích, nhưng không được giả định mọi JWT bất kỳ đều là access token hợp lệ.

**Token được ký không mặc nhiên được mã hóa.** Payload JWS compact thường đọc được qua Base64url, vì vậy không đưa mật khẩu, refresh token, private key, số tài khoản hay dữ liệu nhạy cảm không cần vào claims. Role/entitlement trong JWT cũng có thể **cũ** khi quyền người dùng thay đổi.

Khi signing key hoặc issuer bị nghi xâm phạm, AS phải ngừng cấp token từ nguồn không an toàn và phối hợp để **Resource Server dừng tin key/issuer bị ảnh hưởng**, kể cả JWKS còn cache. Chỉ xoay khóa mà không chặn khóa cũ ở verifier chưa đủ giải quyết lộ private key.

### 7.2. Opaque access token

AS có thể tạo một **chuỗi ngẫu nhiên khó đoán bằng CSPRNG**, ánh xạ nó đến trạng thái token hoặc cơ chế kiểm tra tập trung tương đương. Nó phải có entropy đủ cao để chống đoán, ràng buộc với client, subject, scope, audience, thời hạn và trạng thái thu hồi theo thiết kế.

Resource Server thường xác minh opaque token thông qua **OAuth 2.0 Token Introspection (RFC 7662)**. AS phải bảo vệ endpoint introspection, xác thực/phân quyền Resource Server gọi đến và chỉ trả metadata cần thiết. Phản hồi **active=true** chỉ xác lập trạng thái token theo nguồn tin cậy; API vẫn phải kiểm audience, scope và quyền trên tài nguyên. Cache introspection có thể làm chậm tác dụng thu hồi.

Opaque token hạn chế việc lộ trực tiếp claims qua chuỗi token, nhưng **không làm token bearer an toàn trước bị đánh cắp và replay**. Mọi nơi giữ token phải bảo vệ nó như một credential.

### 7.3. Refresh token

AS chỉ phát refresh token nếu **client/flow/chính sách được phép**, có vòng đời lưu trạng thái và cơ chế thu hồi phù hợp. Refresh token không dành cho API nghiệp vụ; nó chỉ được dùng ở endpoint/flow đổi token của AS. Với các client công khai (public clients), việc bảo vệ refresh token bằng rotation hoặc sender-constraining là cơ chế quan trọng trong hướng dẫn bảo mật OAuth hiện đại.

Token sống lâu hơn có nghĩa việc mất token có thể tạo rủi ro lâu hơn. AS cần cân nhắc hạn dùng tuyệt đối, hết hạn khi không hoạt động, ràng buộc client, phát hiện reuse, khả năng revoke và trải nghiệm đăng nhập lại. Không cấp refresh token chỉ để “có đủ các field” trong response.

### 7.4. OIDC ID token

Trong flow OIDC phù hợp, AS/OpenID Provider có thể cấp ID token cho client. **ID token chứng minh kết quả xác thực danh tính dành cho client**, không có quyền thay access token tại Resource Server. Nó thường chứa những claims bắt buộc như **iss, sub, aud, exp, iat** theo OIDC và có điều kiện bổ sung với **nonce, auth_time** tùy flow/yêu cầu.

Audience của ID token phải hướng về **client ID**, còn audience của access token dành cho API. Trộn hai mục đích này làm tăng rủi ro token substitution.

## 8. Thời hạn, ràng buộc người giữ và quyết định về phiên

Một token có thể được cấp đúng quyền nhưng vẫn không an toàn nếu sống quá lâu hoặc lưu giữ sai. AS cần xác định:

| Thuộc tính | Câu hỏi trước khi phát hành |
|---|---|
| **exp / expires_in** | Access token sống bao lâu dựa trên mức rủi ro, loại client và khả năng thu hồi? |
| **iat / nbf** | Thời điểm tạo/hiệu lực được đặt đúng, có giới hạn clock skew không? |
| **jti hoặc token handle** | Có cần định danh để kiểm toán/thu hồi; ID có đủ duy nhất theo profile không? |
| **Client binding** | Token/grant được cấp cho client nào, có bị đổi nhầm giữa các client không? |
| **Audience và scope** | Có cấp đúng Resource Server, quyền nhỏ nhất và hạn chế mở rộng trong refresh/token exchange không? |
| **Sender-constraining** | Có cần DPoP hoặc mTLS, client và Resource Server có kiểm chứng được proof không? |
| **Revocation** | Ai có thể thu hồi, độ trễ chấp nhận được và các cache kiểm tra token được xử lý ra sao? |
| **Account/consent state** | Quyền/phiên đã bị khóa, đăng xuất hoặc rút ủy quyền có ngăn cấp token mới không? |

**Access token ngắn hạn** giảm cửa sổ rủi ro khi một bearer token bị lộ, nhưng không tự loại bỏ token bị đánh cắp trong thời gian nó còn hiệu lực. **Refresh token rotation**, bảo vệ nơi lưu và sender-constraining (khi áp dụng) xử lý những nguy cơ khác nhau.

Không đặt token vào URL, log, exception, analytics hoặc nơi lưu dễ bị XSS truy cập không kiểm soát. Với ứng dụng trình duyệt, kiến trúc **BFF** và cookie có thuộc tính **HttpOnly, Secure, SameSite** có thể giảm tiếp xúc của token với JavaScript trong trường hợp phù hợp; phải thiết kế bảo vệ CSRF và XSS tương ứng. Với mobile và backend, sử dụng secure storage/secret manager theo khả năng nền tảng.

**Thời hạn access token không bằng thời hạn phiên người dùng.** Một phiên có thể dài hơn access token và được dùng để xin token mới nếu chính sách cho phép; ngược lại, đăng xuất hoặc khóa phiên không tự vô hiệu hóa mọi JWT access token đã phát hành nếu các Resource Server chỉ kiểm tra chữ ký và exp.

## 9. Nguyên tắc thực thi chính sách trước khi trả token

Authorization Server nên có một đường quyết định rõ ràng, thực thi **deny by default** khi thiếu bằng chứng thiết yếu:

~~~mermaid
flowchart TD
    A["Nhận token request"] --> B{"Request và grant type hợp lệ?"}
    B -->|Không| X["Từ chối"]
    B -->|Có| C{"Client đúng và được phép?"}
    C -->|Không| X
    C -->|Có| D{"Grant / code / refresh / client proof hợp lệ?"}
    D -->|Không| X
    D -->|Có| E{"Chủ thể, consent và policy còn cho phép?"}
    E -->|Không| X
    E -->|Có| F{"Scope và resource được chấp thuận?"}
    F -->|Không| X
    F -->|Có| G["Chọn loại token, audience, TTL, key và binding"]
    G --> H{"Có thể cấp an toàn và lưu trạng thái nhất quán?"}
    H -->|Không| X
    H -->|Có| I["Tạo và trả token qua kênh bảo mật"]
~~~

Pseudocode khái niệm:

~~~text
issueToken(request):
    requireHTTPSAndSupportedRequestFormat(request)
    client = identifyClient(request)
    assertGrantAllowed(client, request.grant_type)

    grant = validateProofForGrantType(
        client, request.grant_type, request.credentials
    )
    assertGrantBoundToClientAndNotReplayed(grant, client)

    subject = resolveSubjectAccordingToGrant(grant)
    assertAccountAndAuthorizationPolicy(subject, grant, client)

    approvedScope = evaluateRequestedScopes(
        client, subject, grant, request.scope
    )
    approvedResource = evaluateRequestedResource(
        client, subject, grant, request.resource
    )
    if noPermittedGrant(approvedScope, approvedResource):
        deny()

    tokenPolicy = chooseTokenTypeLifetimeAndProtection(
        client, subject, approvedScope, approvedResource
    )
    assertIssuerKeyAndStorageAreTrusted(tokenPolicy)
    result = atomicallyConsumeGrantAndCreateTokenState(
        grant, tokenPolicy
    )
    return sendTokenResponseOverTLS(result)
~~~

Mã trên **không phải triển khai OAuth có thể dùng trực tiếp**. Nó chỉ cho thấy những kiểm tra cần thiết. Tùy flow, một số điều kiện khác nhau: Client Credentials không có user consent; Refresh Token grant phải chú trọng trạng thái/rotation; Authorization Code phải chứng minh PKCE và code một lần. Các kiểm tra và việc tiêu thụ code/refresh token phải được thực hiện **nhất quán dưới tải đồng thời** để tránh cấp nhiều token từ chứng cứ chỉ được phép dùng một lần.

Trong ứng dụng thật, dùng Authorization Server/framework OAuth/OIDC được duy trì và cấu hình theo tiêu chuẩn/profile, không tự tạo token bằng cách nối JSON với Base64url hoặc tự viết thuật toán chữ ký. Việc cấp quyền phải có audit và chính sách rõ ràng cho các lỗi trước khi phát hành.

## 10. Khi từ chối phát hành: đừng biến lỗi thành quyền

Những tình huống cần xử lý riêng:

| Yêu cầu / bằng chứng | Điều kiện vi phạm | Hành vi kỳ vọng |
|---|---|---|
| Authorization code đã được đổi một lần | Code replay | Không phát token mới; điều tra/revoke liên quan nếu cần |
| Code hợp lệ nhưng PKCE verifier sai | Không chứng minh người đổi code là bên sở hữu verifier | Từ chối |
| Code được cấp cho client A, client B mang đi đổi | Sai client binding | Từ chối |
| Redirect URI không khớp URI đã gắn với code | Sai redirect binding | Từ chối |
| Client không được dùng client_credentials | Grant type chưa được phép | Từ chối |
| Client credentials đã bị thu hồi | Client không còn đáng tin | Từ chối |
| Yêu cầu scope vượt grant hoặc chính sách | Quyền chưa được chấp thuận | Từ chối hoặc cấp scope hẹp theo giao thức/chính sách |
| Resource muốn gọi là Payments nhưng client chỉ có quyền Orders | Audience chưa được chấp thuận | Từ chối/không cấp token cho Payments |
| Refresh token đã vô hiệu hóa | Không còn trạng thái hợp lệ | Từ chối |
| Refresh token cũ được dùng lại sau rotation | Dấu hiệu replay hoặc lỗi đồng bộ | Từ chối và áp dụng chính sách phát hiện reuse/token family |
| User đang bị khóa hoặc quyền đã rút | Ủy quyền gốc không còn chấp nhận | Không cấp token đại diện quyền đã thu hồi |
| Signing key/issuer bị nghi xâm phạm | Gốc tin cậy không an toàn | Ngừng cấp từ nguồn bị ảnh hưởng; xử lý sự cố |

Trong OAuth 2.0 token endpoint, lỗi có thể được biểu diễn bằng mã như **invalid_grant**, **invalid_client**, **invalid_scope**, **unauthorized_client**, **unsupported_grant_type**, tùy nguyên nhân theo chuẩn và profile. Không trả stack trace, client secret, token thật hoặc metadata nhạy cảm trong thông báo lỗi.

Ví dụ một response lỗi đơn giản:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

**Không phải mọi lỗi đều dùng HTTP 400.** Ví dụ xác thực client thất bại có quy tắc HTTP/challenge riêng theo phương thức xác thực. Tránh dùng một ví dụ lỗi để suy quy định cho toàn bộ token endpoint.

## 11. Kết quả phát hành và trách nhiệm sau phát hành

Khi mọi điều kiện thỏa, AS phát hành **token có scope và audience được cấp thực tế**, thường kèm metadata cần thiết:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<opaque-or-JWT-access-token>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read"
}
~~~

Response chỉ mang tính minh họa. Tùy grant và profile, AS có thể cấp thêm **refresh_token** hoặc **id_token** khi thỏa điều kiện; không phải response nào cũng có. **expires_in=900** chỉ là một ví dụ thời hạn 15 phút, không phải giá trị chuẩn bắt buộc.

Tại thời điểm cấp, AS nên ghi **dấu vết kiểm toán đủ an toàn**: issuer, client, loại grant, subject định danh phù hợp, audience/scope được cấp, phiên bản policy/key, thời điểm và mã lý do cấp/từ chối. Không ghi nguyên access token, refresh token, authorization code, code_verifier, private key hoặc mật khẩu vào log.

Sau khi nhận access token, Resource Server còn phải:

- Xác minh nguồn phát hành, chữ ký/JWKS nếu dùng JWT hoặc introspection nếu dùng opaque token.
- Kiểm tra đúng **audience**, loại token, thời hạn và phạm vi quyền.
- Thực thi policy đối với **tài nguyên cụ thể** như tenant, ownership, trạng thái nghiệp vụ.
- Từ chối token bị thu hồi theo thiết kế và không mặc định tin cache đã lỗi thời trong sự cố bảo mật.

**Một token được phát hành hợp lệ vẫn có thể bị từ chối khi sử dụng**: quyền trên tài nguyên đã thay đổi, scope không đủ cho endpoint, token sai audience, hoặc Resource Server đã nhận lệnh thu hồi key/issuer.

## 12. Bài toán thiết kế: Ứng dụng mua sắm và dịch vụ nội bộ

Giả sử có ba thành phần:

| Thành phần | Quyền được phép cấp | Loại client/flow phù hợp |
|---|---|---|
| Ứng dụng web mua sắm | Gọi Orders API, đọc đơn hàng của người dùng | Authorization Code + PKCE, audience orders-api |
| Service tổng hợp báo cáo | Đọc Reports API theo quyền của dịch vụ | Client Credentials, audience reports-api |
| Job hoàn tiền | Gọi Payments API theo chính sách nội bộ | Client Credentials/service identity, audience payments-api |

**Tình huống A – người dùng đăng nhập thành công nhưng yêu cầu quyền hoàn tiền:** client web chỉ được đăng ký dùng orders:read, không được cấp payments:charge; AS phải từ chối hoặc chỉ cấp quyền đã được phép. Không thêm quyền chỉ vì user là người đã xác thực.

**Tình huống B – code Authorization Code bị chặn trên đường redirect:** kẻ tấn công có code nhưng không có **code_verifier**. Token endpoint phải từ chối yêu cầu đổi code vì PKCE không khớp; đồng thời vẫn kiểm client và redirect binding.

**Tình huống C – service báo cáo dùng access token Reports API để gọi Payments API:** Payments API phải từ chối vì audience không phù hợp; service phải xin token riêng nếu chính sách cho phép.

**Tình huống D – refresh token đã bị thu hồi nhưng JWT access token cũ còn hạn:** AS từ chối cấp access token mới; Resource Server có thể vẫn chấp nhận token cũ đến exp nếu không triển khai thu hồi ngay. Thiết kế phải xác định rõ độ trễ chấp nhận được.

**Tình huống E – user bị gỡ khỏi tenant:** AS có thể ngăn token mới hoặc thu hẹp quyền; Resource Server vẫn cần kiểm membership hiện hành cho các thao tác nhạy cảm, vì JWT đã cấp trước đó có thể chứa quyền cũ.

## 13. Checklist trước khi bật một đường cấp token

1. **Flow:** Đây là authorization_code, client_credentials, refresh_token hay flow khác được hỗ trợ? Client có được phép dùng flow đó không?
2. **Client:** Client được nhận diện và xác thực đúng loại hay chưa? Có nhầm public client với confidential client không?
3. **Proof:** Authorization code có còn hạn, dùng một lần, đúng client/redirect/PKCE không? Refresh token có còn hợp lệ và không bị replay?
4. **Người dùng:** Flow có user không? Đã đáp ứng xác thực, độ mới, MFA và trạng thái tài khoản khi policy yêu cầu chưa?
5. **Ủy quyền:** Có consent/ủy quyền hợp lệ khi cần, quyền cấp chưa bị rút và client không vượt quyền không?
6. **Scope:** Scope được cấp có nhỏ nhất có thể và không vượt quyền gốc/client không?
7. **Resource/Audience:** Token dành cho API nào? AS có thẩm quyền cấp cho API đó không?
8. **Định dạng:** Dùng JWT hay opaque? Claims/key/introspection có được xác định đúng profile không?
9. **Thời hạn:** TTL, refresh, expiration, clock skew và chính sách đăng xuất/thu hồi có rõ ràng không?
10. **Bảo vệ credential:** Client/AS/Resource Server có chống rò rỉ, log token, token replay và dùng lại grant không?
11. **Tính nhất quán:** Đổi code/rotation refresh token có được xử lý atomic để chống hai yêu cầu đồng thời không?
12. **Quan sát:** Có thể kiểm tra quyết định cấp/từ chối qua log không chứa secrets, metric và audit không?
13. **Kiểm thử:** Có negative tests cho sai client, sai grant, thiếu PKCE, sai audience/scope, refresh reuse, key bị thu hồi không?

Một hệ thống hoàn chỉnh cần kiểm tra **cả chiều cấp và chiều nhận token**. Đừng đánh giá độ an toàn chỉ bằng việc token endpoint trả về JSON đúng khuôn dạng.

## 14. Tự kiểm tra kiến thức

**1. Người dùng xác thực thành công có đủ để cấp access token cho mọi API không?** Không. AS còn phải kiểm client, grant, scope, resource/audience, quyền cấp và các điều kiện bảo mật.

**2. Authorization Code + PKCE kiểm soát rủi ro nào?** Code được ràng buộc với verifier do client giữ, giúp ngăn kẻ khác chỉ có authorization code đổi thành token; vẫn phải kiểm client, redirect, code một lần và các điều kiện khác.

**3. Client Credentials có cần đăng nhập người dùng không?** Không mặc định. Client xác thực và nhận token theo quyền của chính dịch vụ/client.

**4. Refresh token hợp lệ có thể dùng để xin scope rộng hơn grant gốc không?** Không. AS phải giới hạn scope theo ủy quyền và chính sách ban đầu/hiện hành.

**5. AS cấp JWT access token rồi, Resource Server có thể bỏ qua aud và scope không?** Không. Resource Server phải xác minh token dành cho mình và đủ quyền theo hành động/tài nguyên.

**6. Thu hồi refresh token có làm JWT access token cũ lập tức không hợp lệ không?** Không mặc định. JWT access token tự chứa có thể còn được chấp nhận đến exp nếu không có cơ chế thu hồi bổ sung.

**7. Opaque token có mặc nhiên chống bị đánh cắp không?** Không. Một opaque bearer token còn hoạt động vẫn có thể bị người khác sử dụng; cần bảo vệ nơi lưu, HTTPS, TTL và cơ chế hạn chế replay khi phù hợp.

**8. Vì sao phát refresh token mới phải gắn với việc vô hiệu hóa token cũ?** Để tránh nhiều nhánh token hợp lệ từ cùng credential và tăng khả năng phát hiện reuse/rò rỉ.

**Ghi nhớ:** **Phát hành token không phải phản xạ tự động sau đăng nhập hay sau khi nhận request đúng cú pháp.** Authorization Server chỉ nên cấp token khi đã kiểm **client, grant, chủ thể/ủy quyền, scope, audience, thời hạn và trạng thái tin cậy** phù hợp loại flow. Token được cấp cần có quyền tối thiểu, được bảo vệ và có cơ chế thu hồi; Resource Server tiếp tục xác minh token và đánh giá quyền trên từng tài nguyên khi sử dụng.
